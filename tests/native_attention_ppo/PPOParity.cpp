#include "../../GigaLearn_Project/Native_Attention/AttentionPPO.h"
#include <ATen/Parallel.h>
#include <iostream>

using namespace slater_attention;
Tensor attr(torch::jit::Module& f,const char* name) { return f.attr(name).toTensor(); }
void check_close(const Tensor& got,const Tensor& expected,double tol,const char* name) {
    auto error=(got-expected).abs().max().item<double>();
    std::cout << name << "_max_abs_error " << std::setprecision(12) << error << std::endl;
    if (!std::isfinite(error) || error>tol) throw std::runtime_error(std::string(name)+" parity failed");
}
Batch batch_from(torch::jit::Module& f) {
    Batch b; b.q=attr(f,"q"); b.kv=attr(f,"kv"); b.mask=attr(f,"mask");
    b.action=attr(f,"action"); b.old_logp=attr(f,"old_logp"); b.value=attr(f,"value");
    b.reward=attr(f,"reward"); b.done=attr(f,"done"); b.task=attr(f,"task");
    b.anchor_weight=attr(f,"anchor_weight"); b.bootstrap=.125; return b;
}
void fixture_critic(Engine& engine,torch::jit::Module& f) {
    torch::NoGradGuard guard;
    for (auto item:engine.critic()->named_parameters()) {
        auto name="critic_"+item.key(); std::replace(name.begin(),name.end(),'.','_');
        item.value().copy_(f.attr(name).toTensor());
    }
}
int main(int argc,char** argv) {
    try {
        if(argc!=4) throw std::runtime_error("usage: parity actor.pt fixture_folder output_folder");
        at::set_num_threads(1); torch::manual_seed(12007);
        auto f=torch::jit::load((std::filesystem::path(argv[2])/"fixture.pt").string());
        Config cfg; cfg.epochs=1; cfg.minibatch=8; cfg.shuffle=false;
        Engine engine(argv[1],argv[1],cfg); fixture_critic(engine,f); auto b=batch_from(f);
        // A CPU-only host can test graph portability without pretending CUDA
        // kernels ran: encode cuda:0, serialize, then normalize on CPU load.
        // The original action head must have a real embedded device constant.
        auto portable=torch::jit::load(argv[1],torch::kCPU);
        auto original_weights=cloned_weights(portable);
        auto device_constants=adapt_device_constants(portable,torch::Device(torch::kCUDA,0));
        if(device_constants!=1) throw std::runtime_error("Original actor device constant contract changed");
        auto out=std::filesystem::path(argv[3]); std::filesystem::create_directories(out);
        portable.save((out/"cuda_graph_cpu_weights.pt").string());
        auto encoded=torch::jit::load((out/"cuda_graph_cpu_weights.pt").string(),torch::kCPU);
        size_t encoded_device_methods=0;
        for(auto module:encoded.modules()) for(auto method:module.get_methods())
            encoded_device_methods+=method.graph()->toString().find("value=\"cuda:0\"")!=std::string::npos;
        if(encoded_device_methods!=1) throw std::runtime_error("Serialized device graph was not retained");
        auto normalized=load_attention(out/"cuda_graph_cpu_weights.pt",torch::kCPU);
        auto normalized_weights=cloned_weights(normalized);
        for(size_t i=0;i<original_weights.size();++i)
            if(!torch::equal(original_weights[i],normalized_weights[i])) throw std::runtime_error("Device adaptation changed actor weights");
        check_close(Engine::logits_of(normalized,b.q,b.kv,b.mask),attr(f,"expected_logits"),1e-5,"device_relocation_cpu_logits");
        check_close(engine.logits(b.q,b.kv,b.mask),attr(f,"expected_logits"),1e-5,"logits");
        check_close(engine.values(b.q,b.kv,b.mask,b.task),b.value,1e-6,"critic");
        gae(b); check_close(b.adv,attr(f,"expected_adv"),2e-6,"gae_adv");
        check_close(b.ret,attr(f,"expected_ret"),2e-6,"gae_ret");
        auto before=cloned_weights(engine.actor()); auto metrics=engine.update(b,42);
        check_close(engine.logits(b.q,b.kv,b.mask),attr(f,"expected_after_logits"),5e-5,"after_logits");
        check_close(engine.values(b.q,b.kv,b.mask,b.task),attr(f,"expected_after_values"),2e-5,"after_values");
        auto after=cloned_weights(engine.actor()); size_t changed=0;
        for(size_t i=0;i<before.size();++i) changed+=!torch::equal(before[i],after[i]);
        if(!changed || !engine.teacher_unchanged()) throw std::runtime_error("No learning or teacher mutated");
        write_text(out/"cpp_metrics.json",metrics.json());
        const std::string protocol="{\"fixture\":1}",state="{\"updates\":1,\"seed\":42}";
        engine.save_checkpoint(out/"checkpoint",protocol,state);
        // Save -> reload must restore Adam moments and Torch sampling RNG, not
        // only network weights. Compare the next sample and next full update.
        auto expected_sample=engine.sample(b.q,b.kv,b.mask,b.task);
        auto second=engine.update(b,43);
        auto expected_second=cloned_weights(engine.actor());
        auto expected_values=engine.values(b.q,b.kv,b.mask,b.task).detach();
        Engine resumed(argv[1],argv[1],cfg);
        if(resumed.load_checkpoint(out/"checkpoint",protocol)!=state) throw std::runtime_error("State JSON did not restore");
        auto resumed_sample=resumed.sample(b.q,b.kv,b.mask,b.task);
        if(!torch::equal(resumed_sample.action,expected_sample.action)) throw std::runtime_error("Sampling RNG not restored");
        check_close(resumed_sample.logp,expected_sample.logp,0,"resume_sample_logp");
        auto resumed_second=resumed.update(b,43); auto resumed_weights=cloned_weights(resumed.actor());
        for(size_t i=0;i<expected_second.size();++i) check_close(resumed_weights[i],expected_second[i],0,"resume_actor_weight");
        check_close(resumed.values(b.q,b.kv,b.mask,b.task),expected_values,0,"resume_critic");
        if(second.json()!=resumed_second.json()) throw std::runtime_error("Resume optimizer metrics differ");
        // Force a rejected epoch and verify exact actor+Adam rollback while the
        // critic can retain its supervised updates as in slater_ppo.py.
        Config rejected_cfg=cfg; rejected_cfg.actor_lr=.1; rejected_cfg.target_kl=1e-12; rejected_cfg.max_backtracks=0;
        Engine rejected(argv[1],argv[1],rejected_cfg); fixture_critic(rejected,f);
        auto w=cloned_weights(rejected.actor()); auto opt=optimizer_bytes(rejected.actor_optimizer());
        auto rejected_metrics=rejected.update(b,7);
        if(!rejected_metrics.actor_epoch_rolled_back || rejected_metrics.accepted_actor_epochs) throw std::runtime_error("Expected KL rollback");
        auto rw=cloned_weights(rejected.actor());
        for(size_t i=0;i<w.size();++i) if(!torch::equal(w[i],rw[i])) throw std::runtime_error("Rollback did not restore weights");
        if(rejected.actor_optimizer().state().size()!=0) throw std::runtime_error("Rollback kept Adam moments");
        bool wrong_protocol=false; try{resumed.load_checkpoint(out/"checkpoint","wrong");}catch(...){wrong_protocol=true;}
        if(!wrong_protocol) throw std::runtime_error("Protocol mismatch accepted");
        std::cout << "SLATER_ATTENTION_PPO_PARITY_COMPLETE {\"changed_actor_tensors\":"<<changed
                  <<",\"frozen_teacher_unchanged\":true,\"optimizer_resume_bitexact\":true,\"rng_resume_bitexact\":true,\"rollback_verified\":true,\"device_constant_relocation_verified\":true}"<<std::endl;
        return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<std::endl;return 1;}
}
