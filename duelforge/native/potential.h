// Fast implementation of potential.py's stateless reference estimator.
// This is a kinematic reachability envelope, not a replacement physics engine.
inline float pdf_clip(float x,float lo,float hi){return std::max(lo,std::min(x,hi));}
inline float pdf_len(float x,float y,float z=0){return std::sqrt(x*x+y*y+z*z);}
py::dict predictive_estimate(py::array_t<float,py::array::c_style|py::array::forcecast> world,float horizon,int samples,float temperature,float wi,float wt){
 if(world.ndim()!=3||world.shape(1)!=3||world.shape(2)!=32||samples<8||samples>32||horizon<1||horizon>4||temperature<=0)throw std::invalid_argument("predictive estimate shape/config");
 int n=int(world.shape(0));py::array_t<float> ph(n),eta({n,2}),inter(n),threat(n);py::array_t<bool> reachable({n,2}),quality(n);
 const float*w=world.data();float*ep=eta.mutable_data();bool*rp=reachable.mutable_data();
 {py::gil_scoped_release release;
 for(int i=0;i<n;i++){
  const float*b=w+i*96;float pts[33][3],times[33];int goals[33]={};bool q=true;float p[3]={b[0],b[1],b[2]},v[3]={b[3],b[4],b[5]},spin[3]={b[6],b[7],b[8]},dt=horizon/samples;constexpr float radius=93.15f;
  auto friction=[&](int axis,float direction,float impulse){Vec normal(0,0,0);normal[axis]=direction;Vec contact=normal*(-radius),omega(spin[0],spin[1],spin[2]),vel(v[0],v[1],v[2]),slip=vel+omega.Cross(contact),tangent=slip-normal*slip.Dot(normal),change=tangent*(-1.f/3.5f);float mag=change.Length();change*=std::min(1.f,.35f*impulse/std::max(mag,1e-8f));vel+=change;omega+=contact.Cross(change)/(.4f*radius*radius);for(int k=0;k<3;k++){v[k]=vel[k];spin[k]=omega[k];}return change;};
  for(int j=0;j<=samples;j++){
   times[j]=j*dt;for(int k=0;k<3;k++)pts[j][k]=p[k];if(j==samples)break;
   float damping=std::pow(.97f,dt);for(int k=0;k<3;k++)v[k]*=damping;float oz=p[2],ov=v[2];for(int k=0;k<3;k++)p[k]+=v[k]*dt;p[2]-=325*dt*dt;v[2]-=650*dt;
   if(p[2]<radius){float impact=pdf_clip((ov+std::sqrt(std::max(0.f,ov*ov+1300*std::max(0.f,oz-radius))))/650,0,dt),rem=dt-impact,in=ov-650*impact,up=-.6f*in;p[2]=std::max(radius,radius+up*rem-325*rem*rem);v[2]=up-650*rem;bool settled=std::abs(in)<100;if(settled){p[2]=radius;v[2]=0;}Vec change=friction(2,1,settled?650*dt:std::abs(in)*1.6f);p[0]+=change.x*(settled?dt*.5f:rem);p[1]+=change.y*(settled?dt*.5f:rem);}
   if(p[2]>2044-radius){p[2]=2*(2044-radius)-p[2];float impulse=std::abs(v[2])*1.6f;v[2]=-std::abs(v[2])*.6f;friction(2,-1,impulse);}
   for(int axis=0;axis<2;axis++){
    float limit=(axis==0?4096.f:5120.f)-radius;bool hit=std::abs(p[axis])>limit;
    if(axis==1){bool mouth=std::abs(p[0])<892-radius&&p[2]<642-radius;if(std::abs(p[1])>5120+radius&&mouth)goals[j+1]=p[1]>0?1:-1;hit=hit&&!mouth;}
    if(hit){p[axis]=(p[axis]>=0?1.f:-1.f)*(2*limit-std::abs(p[axis]));float impulse=std::abs(v[axis])*1.6f;v[axis]*=-.6f;friction(axis,p[axis]>0?-1.f:1.f,impulse);}
   }
   float spinMag=pdf_len(spin[0],spin[1],spin[2]);if(spinMag>6)for(int k=0;k<3;k++)spin[k]*=6/spinMag;
   if((std::abs(p[0])>2900&&std::abs(p[1])>3900)||(p[2]<210&&(std::abs(p[0])>3700||std::abs(p[1])>4700)))q=false;
  }
  for(int a=0;a<2;a++){
   const float*c=b+(a+1)*32;bool found=false,oldHeight=false;float oldSlack=0,oldTime=0;ep[i*2+a]=horizon+1;
   float speed=pdf_len(c[3],c[4]),fm=std::max(.05f,pdf_len(c[9],c[10])),fx=c[9]/fm,fy=c[10]/fm,rate=pdf_clip(3.2f-speed*.0008f,1.1f,3.2f),boost=pdf_clip(c[15],0,100);
   bool ground=c[16]>.5f,can=c[29]>.5f;
   for(int j=0;j<=samples;j++){
    float dx=pts[j][0]-c[0],dy=pts[j][1]-c[1],dz=pts[j][2]-c[2],dxy=pdf_len(dx,dy),dist=std::max(1.f,pdf_len(dx,dy,dz)),ux=dx/std::max(dxy,1.f),uy=dy/std::max(dxy,1.f),angle=std::acos(pdf_clip(ux*fx+uy*fy,-1,1)),along=c[3]*ux+c[4]*uy,t=times[j],best=0;
    for(int rev=0;rev<2;rev++){
     float theta=rev?3.14159265358979323846f-angle:angle,turn=theta/rate,available=std::max(0.f,t-turn),dtc=available/8,cap=rev?1200.f:2300.f,cs=std::min(cap,std::max(0.f,along)*std::exp(-theta*.7f)),travel=0,budget=boost;
     for(int k=0;k<8;k++){
      float accel=(rev?1100.f:1600.f)*pdf_clip(1-cs/(rev?1200.f:1410.f),0,1),spend=rev?0:std::min(budget,dtc*33.3f),ab=dtc>0?spend/(33.3f*dtc)*991.7f*dxy/dist:0,next=std::min(cap,cs+(accel+ab)*dtc);
      travel+=(cs+next)*.5f*dtc;cs=next;budget-=spend;
     }
     travel+=std::max(0.f,along)*std::min(t,turn)*.35f;best=std::max(best,travel);
    }
    float fall=c[2]+c[5]*t-325*t*t,jt=std::max(0.f,t-.08f),hold=std::min(jt,.2f),jump=1458*hold*(jt-.5f*hold),vertical=fall+(can?292*jt+(ground?jump+292*std::max(0.f,jt-.35f):0):0),burn=std::min(std::max(0.f,t-.12f),boost/33.3f);
    vertical+=991.7f*std::max(0.f,dz)/dist*burn*(std::max(0.f,t-.12f)-.5f*burn);
    vertical=std::max(vertical,c[2]+(ground?0:std::max(0.f,c[5])*t-325*t*t));
    bool height=pts[j][2]<=std::max(c[2],vertical)+120&&pts[j][2]>=std::max(radius,fall-160)-120;
    if(ground&&!can&&pts[j][2]>c[2]+120)height=false;
    float slack=best+125-dxy;bool feasible=slack>=0&&height&&c[20]<.5f;
    if(j==0)feasible=feasible&&pdf_len(dx,dy,dz)<=125;
    if(feasible){float value=t;if(j>0&&oldHeight&&oldSlack<0){float fraction=pdf_clip(-oldSlack/std::max(1e-6f,slack-oldSlack),0,1);value=oldTime+fraction*(t-oldTime);}ep[i*2+a]=value;found=true;break;}
    oldSlack=slack;oldHeight=height;oldTime=t;
   }
   rp[i*2+a]=found;
  }
  float iv=std::tanh((ep[i*2+1]-ep[i*2])/temperature),tv=0;
  for(int side:{-1,1})for(int j=0;j<=samples;j++)if(goals[j]==side){int defender=side==1?1:0;float arrival=times[j],margin=std::max(0.f,ep[i*2+defender]-arrival);tv+=side*std::tanh(margin/.5f)*std::exp(-arrival/2);break;}
  inter.mutable_data()[i]=iv;threat.mutable_data()[i]=tv;ph.mutable_data()[i]=pdf_clip(wi*iv+wt*tv,-1,1);quality.mutable_data()[i]=q;
 }
 }
 py::dict result;result["phi"]=ph;result["eta"]=eta;result["reachable"]=reachable;result["intercept"]=inter;result["threat"]=threat;result["prediction_quality"]=quality;return result;
}
