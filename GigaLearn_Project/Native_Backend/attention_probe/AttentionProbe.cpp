#include <torch/script.h>
#include <ATen/Parallel.h>
#include <torch/optim/adam.h>
#include <torch/nn/functional/loss.h>
#include <iostream>
#include <iomanip>
#include <vector>
#include <cmath>

torch::Tensor logits(torch::jit::Module& actor, torch::Tensor q, torch::Tensor k, torch::Tensor m) {
    auto input = c10::ivalue::Tuple::create({q, k, m});
    return actor.forward({input}).toTuple()->elements().at(0).toTensor();
}

int main(int argc, char** argv) {
    try {
        if (argc != 4) throw std::runtime_error("usage: probe actor.pt team_inputs.pt duel_inputs.pt");
        at::set_num_threads(1);
        auto student = torch::jit::load(argv[1], torch::kCPU);
        auto teacher = torch::jit::load(argv[1], torch::kCPU);
        student.eval(); teacher.eval();
        std::vector<torch::Tensor> params, before, teacher_before;
        size_t elements = 0;
        for (auto p : student.parameters()) {
            p.set_requires_grad(true); params.push_back(p); before.push_back(p.detach().clone()); elements += p.numel();
        }
        for (auto p : teacher.parameters()) { p.set_requires_grad(false); teacher_before.push_back(p.detach().clone()); }
        if (params.size() != 44 || elements != 444032) throw std::runtime_error("Unexpected actor parameters");
        double max_error = 0;
        for (int index = 2; index < 4; index++) {
            auto inputs = torch::jit::load(argv[index], torch::kCPU);
            auto q = inputs.attr("q").toTensor(), kv = inputs.attr("kv").toTensor(), mask = inputs.attr("mask").toTensor();
            auto expected = inputs.attr("expected").toTensor();
            torch::NoGradGuard guard;
            auto result = logits(student, q, kv, mask);
            auto error = (result - expected).abs().max().item<double>();
            max_error = std::max(max_error, error);
            if (!torch::isfinite(result).all().item<bool>() || error > 1e-5) throw std::runtime_error("Forward parity failed");
        }
        auto inputs = torch::jit::load(argv[2], torch::kCPU);
        auto q = inputs.attr("q").toTensor(), kv = inputs.attr("kv").toTensor(), mask = inputs.attr("mask").toTensor();
        auto initial = logits(student, q, kv, mask);
        auto targets = (initial.detach().argmax(-1) + 17).remainder(90);
        auto loss = torch::nn::functional::cross_entropy(initial, targets);
        torch::optim::Adam optimizer(params, torch::optim::AdamOptions(1e-5));
        optimizer.zero_grad(); loss.backward();
        double grad_sq = 0; size_t gradient_tensors = 0;
        for (auto p : params) if (p.grad().defined()) {
            if (!torch::isfinite(p.grad()).all().item<bool>()) throw std::runtime_error("Nonfinite gradient");
            grad_sq += p.grad().square().sum().item<double>(); gradient_tensors++;
        }
        if (grad_sq <= 0) throw std::runtime_error("No actor gradient");
        optimizer.step();
        size_t changed = 0; double parameter_delta = 0;
        for (size_t index = 0; index < params.size(); index++) {
            auto delta = (params[index].detach() - before[index]).abs().max().item<double>();
            parameter_delta = std::max(parameter_delta, delta); changed += delta > 0;
        }
        if (!changed) throw std::runtime_error("Optimizer did not change actor");
        size_t teacher_index = 0;
        for (auto p : teacher.parameters()) {
            if (!torch::equal(p.detach(), teacher_before.at(teacher_index++)) || p.grad().defined()) throw std::runtime_error("Teacher modified");
        }
        torch::NoGradGuard guard;
        auto updated = logits(student, q, kv, mask);
        double output_delta = (updated - initial.detach()).abs().max().item<double>();
        if (!torch::isfinite(updated).all().item<bool>() || output_delta <= 0) throw std::runtime_error("Updated actor invalid");
        std::cout << std::setprecision(10)
                  << "{\"forward_max_abs_error\":" << max_error
                  << ",\"parameter_tensors\":" << params.size()
                  << ",\"parameter_count\":" << elements
                  << ",\"gradient_tensors\":" << gradient_tensors
                  << ",\"gradient_l2\":" << std::sqrt(grad_sq)
                  << ",\"changed_parameter_tensors\":" << changed
                  << ",\"max_parameter_delta\":" << parameter_delta
                  << ",\"max_logit_delta_after_step\":" << output_delta
                  << ",\"frozen_teacher_unchanged\":true,\"device\":\"cpu\"}" << std::endl;
        return 0;
    } catch(const std::exception& e) { std::cerr << e.what() << std::endl; return 1; }
}
