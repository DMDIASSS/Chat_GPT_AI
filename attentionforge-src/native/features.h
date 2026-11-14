// Public-state encoder. Same 43x40 contract as observation.encode_reference.
// No opponent controls, simulator-private jump clocks or future state.
inline py::tuple encode_native(
 py::array_t<float,py::array::c_style|py::array::forcecast> world,
 py::array_t<float,py::array::c_style|py::array::forcecast> pads,
 py::array_t<float,py::array::c_style|py::array::forcecast> locations) {
 if(world.ndim()!=3||world.shape(2)!=32||pads.ndim()!=3||pads.shape(0)!=world.shape(0)||pads.shape(1)!=34||pads.shape(2)!=2||locations.ndim()!=2||locations.shape(0)!=34||locations.shape(1)!=4)
  throw std::invalid_argument("Invalid public observation shapes");
 int e=int(world.shape(0)),n=int(world.shape(1))-1,team=n/2;
 if(n!=2&&n!=4&&n!=6)throw std::invalid_argument("Only balanced 1v1, 2v2, 3v3 supported");
 py::array_t<float> tokens({e,n,43,40});py::array_t<bool> legal({e,n,90});
 const float*w=world.data(),*ps=pads.data(),*loc=locations.data();float*out=tokens.mutable_data();bool*mask=legal.mutable_data();auto table=actions();
 {py::gil_scoped_release release;
 std::fill(out,out+tokens.size(),0.f);
 for(int i=0;i<e;i++)for(int a=0;a<n;a++){
  const float*ego=w+(i*(n+1)+a+1)*32;float sign=a<team?1.f:-1.f;
  float right[3]={ego[13]*ego[11]-ego[14]*ego[10],ego[14]*ego[9]-ego[12]*ego[11],ego[12]*ego[10]-ego[13]*ego[9]};
  int slots[43];std::fill(slots,slots+43,-1);slots[0]=a+1;slots[1]=0;int al=2,op=4;
  for(int b=0;b<n;b++)if(b!=a){if((b<team)==(a<team))slots[al++]=b+1;else slots[op++]=b+1;}
  for(int k=0;k<43;k++){
   float local[32]={};const float*s=nullptr;int type=0;
   if(slots[k]>=0){s=w+(i*(n+1)+slots[k])*32;type=k==0?1:(k==1?2:(k<4?3:4));}
   else if(k>=7&&k<41){for(int j=0;j<3;j++)local[j]=loc[(k-7)*4+j];s=local;type=5;}
   else if(k>=41){local[1]=(k==41?-sign:sign)*5120;local[2]=300;s=local;type=6;}
   else continue;
   float*q=out+((i*n+a)*43+k)*40;
   for(int field=0;field<3;field++){
    float v[3];for(int j=0;j<3;j++)v[j]=field==0?s[j]-ego[j]:(field==1?(k==0?s[j+3]:s[j+3]-ego[j+3]):s[j+6]);
    float scale=field==0?4096.f:(field==1?2300.f:5.5f);
    q[field*3]=(v[0]*ego[9]+v[1]*ego[10]+v[2]*ego[11])/scale;
    q[field*3+1]=(v[0]*right[0]+v[1]*right[1]+v[2]*right[2])/scale;
    q[field*3+2]=(v[0]*ego[12]+v[1]*ego[13]+v[2]*ego[14])/scale;
   }
   if(k!=1)for(int j=9;j<15;j++)q[j]=s[j]*(j%3==2?1.f:sign);
   q[15]=s[15]/100;for(int j=16;j<21;j++)q[j]=s[j];q[23]=1-s[18];
   q[24]=s[0]*sign/4096;q[25]=s[1]*sign/5120;q[26]=s[2]/2044;
   if(type==5){int b=k-7;q[28]=loc[b*4+3];q[29]=ps[i*68+b*2];q[30]=ps[i*68+b*2+1]/10;}
   if(type==6)q[28]=k==41?-1.f:1.f;
   if(k==0)for(int j=0;j<8;j++)q[31+j]=ego[21+j];q[39]=float(type);
  }
  bool noJump=ego[18]>.5f||ego[20]>.5f;
  for(int j=0;j<90;j++)mask[(i*n+a)*90+j]=!(noJump&&table[j].jump)&&!(ego[15]<=0&&table[j].boost);
 }
 }return py::make_tuple(tokens,legal);
}
