#pragma once
#include <torch/types.h>
#include <vector>
#include <algorithm>
#include <sstream>
#include <stdexcept>
#define RS_MAX(a,b) std::max(a,b)
#define RS_CLAMP(a,b,c) std::clamp(a,b,c)
#define RG_ERR_CLOSE(msg) {std::ostringstream ss;ss<<msg;throw std::runtime_error(ss.str());}
namespace RLGC {enum TerminalType {NOT_TERMINAL,NORMAL,TRUNCATED};}
namespace GGL::GAE {void Compute(torch::Tensor,torch::Tensor,torch::Tensor,torch::Tensor,torch::Tensor&,torch::Tensor&,torch::Tensor&,float&,float,float,float,float);}
