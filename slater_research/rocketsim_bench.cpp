// Standalone PHYSICS-only throughput benchmark against ZealanL/RocketSim.
// Build in your existing RocketSim CMake tree with RocketSim library headers/linkage.
// IMPORTANT: no neural inference, serialization, reward, or RLViser in this test.
#include "RocketSim.h"
#include <algorithm>
#include <cstdint>
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <thread>
#include <vector>

int main(int argc, char** argv) {
    const unsigned workers = argc > 1 ? std::max(1, std::atoi(argv[1])) : 32;
    const int seconds = argc > 2 ? std::max(1, std::atoi(argv[2])) : 10;
    RocketSim::Init("collision_meshes", true); // initialize once, before spawning threads
    std::atomic<bool> running{true};
    std::atomic<std::uint64_t> tick_count{0};
    std::vector<std::thread> threads;
    threads.reserve(workers);
    for (unsigned tid=0; tid<workers; ++tid) {
        threads.emplace_back([&, tid] {
            std::unique_ptr<RocketSim::Arena> arena(
                RocketSim::Arena::Create(RocketSim::GameMode::SOCCAR));
            auto* blue = arena->AddCar(RocketSim::Team::BLUE);
            auto* orange = arena->AddCar(RocketSim::Team::ORANGE);
            blue->controls.throttle = 1.f;
            orange->controls.throttle = 1.f;
            arena->ResetToRandomKickoff(static_cast<int>(tid));
            std::uint64_t local_ticks=0;
            while(running.load(std::memory_order_relaxed)) {
                arena->Step(8); // counts eight 120Hz PHYSICS ticks
                local_ticks += 8;
                // Avoid immediate goal/terminal pile-up in long-running sim.
                if (arena->tickCount % 4096 == 0) {
                    arena->ResetToRandomKickoff(static_cast<int>(tid + local_ticks));
                }
            }
            tick_count.fetch_add(local_ticks,std::memory_order_relaxed);
        });
    }
    const auto started=std::chrono::steady_clock::now();
    std::this_thread::sleep_for(std::chrono::seconds(seconds));
    running.store(false,std::memory_order_relaxed);
    for (auto& t:threads)t.join();
    const double elapsed=std::chrono::duration<double>(
        std::chrono::steady_clock::now()-started).count();
    const double tps=tick_count.load()/elapsed;
    std::cout << "arenas=" << workers << " elapsed=" << elapsed
              << " physics_ticks_per_sec=" << tps
              << " decisions_per_sec_at_repeat8=" << tps/8.0 << "\n";
}
