#include "GAE.h"
#include <iostream>
int main(int argc,char** argv){
 bool terminal=argc<2||std::string(argv[1])=="terminal";
 auto r=torch::tensor({0.f,0.f});
 auto t=torch::tensor(std::vector<int8_t>{2,int8_t(terminal?1:2)});
 auto v=torch::tensor({0.f,0.f});
 auto tv=torch::tensor(terminal?std::vector<float>{10.f}:std::vector<float>{10.f,100.f});
 torch::Tensor adv,targets,returns;float clipped=0;
 GGL::GAE::Compute(r,t,v,tv,adv,targets,returns,clipped,1.f,0.f,0.f,0.f);
 std::cout<<"ADVANTAGES="<<adv<<"\n";
 if(!terminal){auto expected=torch::tensor({10.f,100.f});std::cout<<"MATCH="<<torch::allclose(adv,expected)<<"\n";return torch::allclose(adv,expected)?0:2;}
 return 0;
}
