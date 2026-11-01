#include "../../GigaLearn_Project/Native_Attention/AttentionEval.h"
#include <ATen/Parallel.h>
int main(int argc, char** argv) {
    try {
        if (argc != 6) throw std::runtime_error("manifest meshes out pause worlds");
        at::set_num_threads(1); at::set_num_interop_threads(1);
        auto result = slater_attention_eval::run_batched_evaluation(argv[1], argv[2], argv[3],
            torch::Device(torch::kCPU), argv[4], std::stoi(argv[5]), 2);
        std::cout << "SLATER_SELECTOR_COMPLETE " << result.dump() << std::endl;
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << std::endl; return 1;
    }
}
