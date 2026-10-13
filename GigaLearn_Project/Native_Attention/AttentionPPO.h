#pragma once

// Original attention policy PPO. The 90 Nexto actions are deliberately unmasked.
#include <torch/script.h>
#include <torch/csrc/jit/runtime/graph_executor.h>
#include <ATen/Context.h>
#include <torch/optim/adam.h>
#include <torch/nn/module.h>
#include <torch/nn/modules/linear.h>
#include <torch/nn/modules/container/sequential.h>
#include <torch/nn/modules/activation.h>
#include <torch/nn/utils/clip_grad.h>
#include <torch/serialize/archive.h>
#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <numeric>
#include <random>
#include <sstream>
#include <stdexcept>

namespace slater_attention {

using Tensor = torch::Tensor;
struct Config {
    double actor_lr = 1e-5, critic_lr = 1e-4, teacher_weight = .03;
    double target_kl = .015, gamma = .995, lambda = .95;
    int epochs = 2, minibatch = 256, max_backtracks = 3;
    bool shuffle = true;
};
struct Batch {
    Tensor q, kv, mask, action, old_logp, value, reward, done, task;
    Tensor adv, ret, anchor_weight;
    double bootstrap = 0;
    int64_t size() const { return action.numel(); }
};
struct Choice { Tensor action, logp, value; };
struct Metrics {
    double actor_loss = 0, value_loss = 0, teacher_kl = 0, entropy = 0, clip_fraction = 0;
    double rollout_policy_kl = 0, target_kl = 0, actor_learning_rate = 0;
    double rejected_policy_kl = 0;
    int accepted_actor_epochs = 0, attempted_epochs = 0, learning_rate_backtracks = 0;
    bool actor_epoch_rolled_back = false;
    std::string json() const {
        std::ostringstream out; out << std::setprecision(17)
            << "{\"actor_loss\":" << actor_loss << ",\"value_loss\":" << value_loss
            << ",\"teacher_kl\":" << teacher_kl << ",\"entropy\":" << entropy
            << ",\"clip_fraction\":" << clip_fraction << ",\"rollout_policy_kl\":" << rollout_policy_kl
            << ",\"target_kl\":" << target_kl << ",\"accepted_actor_epochs\":" << accepted_actor_epochs
            << ",\"attempted_epochs\":" << attempted_epochs
            << ",\"actor_epoch_rolled_back\":" << (actor_epoch_rolled_back ? "true" : "false")
            << ",\"rejected_policy_kl\":";
        if (actor_epoch_rolled_back) out << rejected_policy_kl; else out << "null";
        out << ",\"learning_rate_backtracks\":" << learning_rate_backtracks
            << ",\"actor_learning_rate\":" << actor_learning_rate << "}";
        return out.str();
    }
};

inline void finite(const Tensor& x, const char* name) {
    if (!x.defined() || !torch::isfinite(x).all().item<bool>())
        throw std::runtime_error(std::string("Missing or nonfinite ") + name);
}

// Reverse recursion is done in doubles like the NumPy/Python reference and
// stored in float32 after each step. Terminal boundaries never bootstrap.
inline std::pair<Tensor, Tensor> gae(const Tensor& rewards, const Tensor& values,
                                    const Tensor& dones, double bootstrap,
                                    double gamma = .995, double lambda = .95) {
    finite(rewards, "rewards"); finite(values, "values"); finite(dones, "dones");
    if (!std::isfinite(bootstrap) || rewards.dim() != 1 || rewards.numel() == 0 ||
        rewards.sizes() != values.sizes() || values.sizes() != dones.sizes())
        throw std::runtime_error("Bad GAE vectors");
    auto r = rewards.to(torch::kCPU, torch::kFloat32).contiguous();
    auto v = values.to(torch::kCPU, torch::kFloat32).contiguous();
    auto d = dones.to(torch::kCPU, torch::kFloat32).contiguous();
    auto a = torch::zeros_like(r);
    auto rp = r.data_ptr<float>(), vp = v.data_ptr<float>(), dp = d.data_ptr<float>(), ap = a.data_ptr<float>();
    double acc = 0;
    for (int64_t i = r.numel() - 1; i >= 0; --i) {
        if (dp[i] != 0 && dp[i] != 1) throw std::runtime_error("GAE done must be binary");
        double next = i + 1 < r.numel() ? vp[i + 1] : bootstrap;
        double keep = 1. - dp[i];
        double delta = rp[i] + gamma * keep * next - vp[i];
        acc = delta + gamma * lambda * keep * acc;
        ap[i] = static_cast<float>(acc);
    }
    return {a.to(rewards.device()), (a + v).to(rewards.device())};
}
inline void gae(Batch& b, double gamma = .995, double lambda = .95) {
    auto result = gae(b.reward, b.value, b.done, b.bootstrap, gamma, lambda);
    b.adv = result.first; b.ret = result.second;
}

struct CriticImpl : torch::nn::Module {
    torch::nn::Sequential body;
    torch::nn::Linear heads{nullptr};
    CriticImpl() {
        body = register_module("body", torch::nn::Sequential(
            torch::nn::Linear(80, 192), torch::nn::Tanh(),
            torch::nn::Linear(192, 192), torch::nn::Tanh()));
        heads = register_module("heads", torch::nn::Linear(192, 12));
    }
    Tensor forward(const Tensor& q, const Tensor& kv, const Tensor& mask, const Tensor& task) {
        auto valid = mask.eq(0).unsqueeze(-1).to(kv.scalar_type());
        auto pooled = (kv * valid).sum(1) / valid.sum(1).clamp_min(1);
        auto bi = kv.select(2, 3).argmax(1);
        auto ball = kv.gather(1, bi.reshape({-1, 1, 1}).expand({kv.size(0), 1, 24})).squeeze(1);
        auto features = torch::cat({q.select(1, 0), pooled, ball}, -1);
        auto all_values = heads(body->forward(features));
        return all_values.gather(1, task.reshape({-1, 1})).squeeze(1);
    }
};
TORCH_MODULE(Critic);

inline std::vector<Tensor> parameters(torch::jit::Module& m) {
    std::vector<Tensor> result;
    for (auto p : m.parameters()) result.push_back(p);
    return result;
}
inline std::vector<Tensor> cloned_weights(torch::jit::Module& m) {
    std::vector<Tensor> result;
    for (auto p : m.parameters()) result.push_back(p.detach().clone());
    for (auto p : m.buffers()) result.push_back(p.detach().clone());
    return result;
}
inline void restore_weights(torch::jit::Module& m, const std::vector<Tensor>& data) {
    torch::NoGradGuard guard; size_t i = 0;
    for (auto p : m.parameters()) p.copy_(data.at(i++));
    for (auto p : m.buffers()) p.copy_(data.at(i++));
}
inline std::string optimizer_bytes(torch::optim::Adam& optimizer) {
    torch::serialize::OutputArchive archive; optimizer.save(archive);
    std::ostringstream stream(std::ios::binary); archive.save_to(stream); return stream.str();
}
inline void restore_optimizer(torch::optim::Adam& optimizer, const std::string& data, torch::Device device) {
    torch::serialize::InputArchive archive;
    std::istringstream stream(data, std::ios::binary); archive.load_from(stream, device);
    // C++ Adam::load merges its state map. A rollback must replace it,
    // including restoring the empty pre-first-update state.
    optimizer.state().clear();
    optimizer.load(archive);
}
inline std::string read_text(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("Cannot read " + path.string());
    return {std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>()};
}
inline void write_text(const std::filesystem::path& path, const std::string& text) {
    std::ofstream out(path, std::ios::binary); out << text; out.close();
    if (!out) throw std::runtime_error("Cannot write " + path.string());
}

class Engine {
    torch::jit::Module actor_, teacher_;
    Critic critic_;
    Config cfg_;
    torch::Device device_;
    std::vector<Tensor> teacher_initial_;
    std::unique_ptr<torch::optim::Adam> actor_opt_, critic_opt_;

    void bind_optimizers() {
        actor_opt_ = std::make_unique<torch::optim::Adam>(parameters(actor_), torch::optim::AdamOptions(cfg_.actor_lr));
        critic_opt_ = std::make_unique<torch::optim::Adam>(critic_->parameters(), torch::optim::AdamOptions(cfg_.critic_lr));
    }
    double actor_lr() const {
        return static_cast<const torch::optim::AdamOptions&>(actor_opt_->param_groups().at(0).options()).lr();
    }
    void set_actor_lr(double lr) {
        for (auto& group : actor_opt_->param_groups()) static_cast<torch::optim::AdamOptions&>(group.options()).lr(lr);
    }
    Tensor rollout_logp(const Batch& b) {
        torch::NoGradGuard guard; std::vector<Tensor> parts;
        for (int64_t start = 0; start < b.size(); start += cfg_.minibatch) {
            auto count = std::min<int64_t>(cfg_.minibatch, b.size() - start);
            parts.push_back(logits(b.q.narrow(0,start,count), b.kv.narrow(0,start,count), b.mask.narrow(0,start,count)).log_softmax(-1));
        }
        return torch::cat(parts);
    }
    Metrics epoch(Batch& b, uint64_t seed) {
        std::vector<int64_t> order(b.size()); std::iota(order.begin(), order.end(), 0);
        if (cfg_.shuffle) { std::mt19937_64 rng(seed); std::shuffle(order.begin(), order.end(), rng); }
        // NumPy array_split balances minibatch sizes rather than leaving a tiny final batch.
        auto chunks = std::max<int64_t>(1, (b.size() + cfg_.minibatch - 1) / cfg_.minibatch);
        auto small = b.size() / chunks, extra = b.size() % chunks;
        Metrics sum; int64_t start = 0;
        for (int64_t c = 0; c < chunks; ++c) {
            auto count = small + (c < extra);
            auto ix = torch::tensor(std::vector<int64_t>(order.begin()+start, order.begin()+start+count), torch::TensorOptions().dtype(torch::kInt64).device(device_)); start += count;
            auto q = b.q.index_select(0,ix), k = b.kv.index_select(0,ix), m = b.mask.index_select(0,ix);
            auto live = logits(q,k,m);
            Tensor fixed;
            { torch::NoGradGuard guard; fixed = logits_of(teacher_,q,k,m); }
            auto log_probs = live.log_softmax(-1), probs = log_probs.exp();
            auto logp = log_probs.gather(1,b.action.index_select(0,ix).unsqueeze(1)).squeeze(1);
            auto ratio = (logp - b.old_logp.index_select(0,ix)).exp();
            auto adv = b.adv.index_select(0,ix);
            auto surrogate = torch::minimum(ratio * adv, ratio.clamp(.85,1.15) * adv).mean();
            auto teacher_logp = (fixed / 1.5).log_softmax(-1);
            auto per_kl = (teacher_logp.exp() * (teacher_logp - (live / 1.5).log_softmax(-1))).sum(-1) * 2.25;
            auto kl = per_kl.mean();
            auto anchor = b.anchor_weight.defined() ? (per_kl * b.anchor_weight.index_select(0,ix)).mean() : cfg_.teacher_weight * kl;
            auto entropy = -(probs * log_probs).sum(-1).mean();
            auto actor_loss = -surrogate + anchor - .003 * entropy;
            finite(actor_loss,"actor loss");
            actor_opt_->zero_grad(true); actor_loss.backward();
            torch::nn::utils::clip_grad_norm_(parameters(actor_), .5, 2., true); actor_opt_->step();
            auto v = values(q,k,m,b.task.index_select(0,ix));
            auto err = (v - b.ret.index_select(0,ix)).abs();
            auto value_loss = torch::where(err < 1., .5 * err.square(), err - .5).mean();
            finite(value_loss,"value loss"); critic_opt_->zero_grad(true); value_loss.backward();
            torch::nn::utils::clip_grad_norm_(critic_->parameters(), .5, 2., true); critic_opt_->step();
            sum.actor_loss += actor_loss.item<double>(); sum.value_loss += value_loss.item<double>();
            sum.teacher_kl += kl.item<double>(); sum.entropy += entropy.item<double>();
            sum.clip_fraction += (ratio.detach()-1).abs().gt(.15).to(torch::kFloat32).mean().item<double>();
        }
        sum.actor_loss /= chunks; sum.value_loss /= chunks; sum.teacher_kl /= chunks;
        sum.entropy /= chunks; sum.clip_fraction /= chunks;
        return sum;
    }
    void validate_batch(Batch& b) {
        int64_t n = b.size(); if (n < 1) throw std::runtime_error("Empty rollout");
        if (b.q.dim()!=3 || b.q.size(0)!=n || b.q.size(1)!=1 || b.q.size(2)!=32 ||
            b.kv.dim()!=3 || b.kv.size(0)!=n || b.kv.size(2)!=24 ||
            b.mask.dim()!=2 || b.mask.size(0)!=n || b.mask.size(1)!=b.kv.size(1))
            throw std::runtime_error("Bad attention observation batch shapes");
        finite(b.q,"q"); finite(b.kv,"kv"); finite(b.mask,"mask");
        if (!b.task.defined()) b.task=torch::zeros({n},torch::TensorOptions().dtype(torch::kLong).device(device_));
        b.action=b.action.to(device_,torch::kLong); b.task=b.task.to(device_,torch::kLong);
        if (b.action.dim()!=1 || b.task.dim()!=1 || b.task.numel()!=n ||
            b.action.lt(0).any().item<bool>() || b.action.ge(90).any().item<bool>() ||
            b.task.lt(0).any().item<bool>() || b.task.ge(12).any().item<bool>())
            throw std::runtime_error("Invalid action or task IDs");
        for (auto* item : {&b.q,&b.kv,&b.mask,&b.old_logp,&b.value,&b.reward,&b.done,&b.adv,&b.ret,&b.anchor_weight})
            if (item->defined()) *item=item->to(device_,torch::kFloat32);
        if (!b.adv.defined() || !b.ret.defined()) gae(b,cfg_.gamma,cfg_.lambda);
        for (auto* item : {&b.old_logp,&b.adv,&b.ret}) {
            finite(*item,"rollout vector");
            if (item->dim()!=1 || item->numel()!=n) throw std::runtime_error("Bad rollout vector size");
        }
        if (b.anchor_weight.defined()) {
            finite(b.anchor_weight,"anchor weights");
            if (b.anchor_weight.dim()!=1 || b.anchor_weight.numel()!=n || b.anchor_weight.lt(0).any().item<bool>())
                throw std::runtime_error("Invalid anchor weights");
        }
        b.adv = (b.adv - b.adv.mean()) / (b.adv.std(false) + 1e-7);
    }
public:
    Engine(const std::filesystem::path& actor_path, const std::filesystem::path& teacher_path,
           Config cfg = {}, torch::Device device = torch::kCPU)
        : actor_(torch::jit::load(actor_path.string(),device)),
          teacher_(torch::jit::load(teacher_path.string(),device)), cfg_(cfg), device_(device) {
        if (!(cfg.actor_lr>0 && std::isfinite(cfg.actor_lr) && cfg.critic_lr>0 && std::isfinite(cfg.critic_lr) &&
              cfg.target_kl>0 && std::isfinite(cfg.target_kl) && cfg.teacher_weight>=0 && std::isfinite(cfg.teacher_weight)) ||
            cfg.epochs<1 || cfg.minibatch<1 || cfg.max_backtracks<0 || cfg.max_backtracks>8)
            throw std::runtime_error("Invalid attention PPO configuration");
        // Avoid profiling/fusion warmup changing floating-point gradients after reload.
        torch::jit::setGraphExecutorOptimize(false);
        actor_.eval(); teacher_.eval(); critic_->to(device_);
        for (auto p : actor_.parameters()) p.set_requires_grad(true);
        for (auto p : teacher_.parameters()) p.set_requires_grad(false);
        teacher_initial_=cloned_weights(teacher_); bind_optimizers();
    }
    static Tensor logits_of(torch::jit::Module& actor, const Tensor& q, const Tensor& kv, const Tensor& mask) {
        auto output=actor.forward({c10::ivalue::Tuple::create({q,kv,mask})});
        auto result=output.isTuple() ? output.toTuple()->elements().at(0).toTensor() : output.toTensor();
        finite(result,"attention logits");
        if (result.dim()!=2 || result.size(0)!=q.size(0) || result.size(1)!=90)
            throw std::runtime_error("Attention actor must return 90 unmasked action logits");
        return result;
    }
    Tensor logits(const Tensor& q,const Tensor& kv,const Tensor& mask) { return logits_of(actor_,q,kv,mask); }
    Tensor values(const Tensor& q,const Tensor& kv,const Tensor& mask,const Tensor& task) { return critic_->forward(q,kv,mask,task); }
    Choice sample(const Tensor& q,const Tensor& kv,const Tensor& mask,const Tensor& task) {
        torch::NoGradGuard guard; auto lp=logits(q,kv,mask).log_softmax(-1);
        auto action=torch::multinomial(lp.exp(),1).squeeze(1);
        return {action,lp.gather(1,action.unsqueeze(1)).squeeze(1),values(q,kv,mask,task)};
    }
    bool teacher_unchanged() {
        auto current=cloned_weights(teacher_); if (current.size()!=teacher_initial_.size()) return false;
        for (size_t i=0;i<current.size();++i) if (!torch::equal(current[i],teacher_initial_[i])) return false;
        for (auto p:teacher_.parameters()) if (p.grad().defined()) return false;
        return true;
    }
    Metrics update(Batch batch,uint64_t seed) {
        // The Python trainer restores its configured LR once per update.
        set_actor_lr(cfg_.actor_lr);
        validate_batch(batch); auto old_logp=rollout_logp(batch); auto old_prob=old_logp.exp();
        Metrics result; result.target_kl=cfg_.target_kl;
        for (int e=0;e<cfg_.epochs;++e) {
            result.attempted_epochs=e+1;
            auto weights=cloned_weights(actor_); auto optimizer=optimizer_bytes(*actor_opt_); double lr=actor_lr();
            Metrics last; double drift=0;
            try {
                for (int attempt=0;attempt<=cfg_.max_backtracks;++attempt) {
                    restore_weights(actor_,weights); restore_optimizer(*actor_opt_,optimizer,device_);
                    set_actor_lr(lr * std::pow(.5,attempt)); last=epoch(batch,seed+e);
                    auto next=rollout_logp(batch);
                    drift=(old_prob*(old_logp-next)).sum(-1).mean().item<double>();
                    if (!std::isfinite(drift)) throw std::runtime_error("Nonfinite rollout KL");
                    if (drift<=cfg_.target_kl) break;
                    if (attempt<cfg_.max_backtracks) result.learning_rate_backtracks++;
                }
            } catch (...) {
                restore_weights(actor_,weights); restore_optimizer(*actor_opt_,optimizer,device_);
                actor_opt_->zero_grad(true); throw;
            }
            if (drift>cfg_.target_kl) {
                restore_weights(actor_,weights); restore_optimizer(*actor_opt_,optimizer,device_); actor_opt_->zero_grad(true);
                result.actor_epoch_rolled_back=true; result.rejected_policy_kl=drift; break;
            }
            result.rollout_policy_kl=std::max(0.,drift); result.accepted_actor_epochs++;
            result.actor_loss+=last.actor_loss; result.value_loss+=last.value_loss;
            result.teacher_kl+=last.teacher_kl; result.entropy+=last.entropy; result.clip_fraction+=last.clip_fraction;
        }
        if (result.accepted_actor_epochs) {
            auto n=result.accepted_actor_epochs; result.actor_loss/=n; result.value_loss/=n;
            result.teacher_kl/=n; result.entropy/=n; result.clip_fraction/=n;
        }
        result.actor_learning_rate=actor_lr();
        if (!teacher_unchanged()) throw std::runtime_error("Frozen attention teacher changed");
        return result;
    }
    torch::jit::Module& actor() { return actor_; }
    torch::jit::Module& teacher() { return teacher_; }
    Critic& critic() { return critic_; }
    torch::optim::Adam& actor_optimizer() { return *actor_opt_; }
    torch::optim::Adam& critic_optimizer() { return *critic_opt_; }
    const Config& config() const { return cfg_; }
    torch::Device device() const { return device_; }

    // A directory becomes resumable only after all full-state files and the
    // completion marker have been written, then renamed on the same filesystem.
    void save_checkpoint(const std::filesystem::path& destination,const std::string& protocol_json,const std::string& state_json) {
        if (!teacher_unchanged()) throw std::runtime_error("Refusing checkpoint with changed teacher");
        auto partial=destination; partial += ".partial";
        if (std::filesystem::exists(destination) || std::filesystem::exists(partial))
            throw std::runtime_error("Checkpoint destination already exists");
        std::filesystem::create_directories(partial);
        try {
            actor_.save((partial/"actor.pt").string()); teacher_.save((partial/"teacher.pt").string());
            torch::serialize::OutputArchive c,aopt,copt,rng;
            critic_->save(c); c.save_to((partial/"critic.pt").string());
            actor_opt_->save(aopt); aopt.save_to((partial/"actor_optimizer.pt").string());
            critic_opt_->save(copt); copt.save_to((partial/"critic_optimizer.pt").string());
            rng.write("cpu",at::globalContext().defaultGenerator(torch::kCPU).get_state(),true);
            if (device_.is_cuda()) rng.write("device",at::globalContext().defaultGenerator(device_).get_state(),true);
            rng.save_to((partial/"rng.pt").string());
            write_text(partial/"protocol.json",protocol_json); write_text(partial/"state.json",state_json);
            write_text(partial/"FORMAT.json","{\"format\":\"slater-attention-full-v1\",\"action_count\":90,\"critic_heads\":12}\n");
            write_text(partial/"COMPLETE","slater-attention-full-v1\n");
            std::filesystem::rename(partial,destination);
        } catch (...) {
            // Retain a failed partial for diagnosis; never present it as complete.
            throw;
        }
    }
    std::string load_checkpoint(const std::filesystem::path& source,const std::string& expected_protocol_json) {
        if (read_text(source/"COMPLETE")!="slater-attention-full-v1\n" || read_text(source/"protocol.json")!=expected_protocol_json)
            throw std::runtime_error("Incomplete checkpoint or incompatible protocol");
        auto new_actor=torch::jit::load((source/"actor.pt").string(),device_);
        auto new_teacher=torch::jit::load((source/"teacher.pt").string(),device_);
        auto loaded_teacher=cloned_weights(new_teacher);
        if (loaded_teacher.size()!=teacher_initial_.size()) throw std::runtime_error("Checkpoint teacher architecture changed");
        for (size_t i=0;i<loaded_teacher.size();++i)
            if (!torch::equal(loaded_teacher[i],teacher_initial_[i])) throw std::runtime_error("Checkpoint frozen teacher differs");
        actor_=std::move(new_actor); teacher_=std::move(new_teacher); actor_.eval(); teacher_.eval();
        for (auto p:actor_.parameters()) p.set_requires_grad(true);
        for (auto p:teacher_.parameters()) p.set_requires_grad(false);
        torch::serialize::InputArchive c,aopt,copt,rng;
        c.load_from((source/"critic.pt").string(),device_); critic_->load(c); bind_optimizers();
        aopt.load_from((source/"actor_optimizer.pt").string(),device_); actor_opt_->load(aopt);
        copt.load_from((source/"critic_optimizer.pt").string(),device_); critic_opt_->load(copt);
        rng.load_from((source/"rng.pt").string(),torch::kCPU); Tensor cpu; rng.read("cpu",cpu,true);
        auto cpu_generator=at::globalContext().defaultGenerator(torch::kCPU); cpu_generator.set_state(cpu);
        if (device_.is_cuda()) { Tensor gpu; rng.read("device",gpu,true); auto generator=at::globalContext().defaultGenerator(device_); generator.set_state(gpu); }
        return read_text(source/"state.json");
    }
};
}  // namespace slater_attention
