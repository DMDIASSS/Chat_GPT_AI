#pragma once
// Cheap unobstructed shot proxy. Finite, bounded and team-symmetric; it is not
// a collision predictor or a probability of beating the goalkeeper.
inline float attack_shot_quality(Vec p,Vec v,int team){
 float sign=team? -1.f:1.f;float speed=sign*v.y;
 if(speed<=100)return 0;float t=(5120.f-sign*p.y)/speed;if(t<=0||t>3)return 0;
 float x=p.x+t*v.x,z;
 if(p.z<110&&std::abs(v.z)<100)z=94;
 else {float h=std::max(0.f,p.z-94);float fall=(v.z+std::sqrt(v.z*v.z+1300*h))/650;
  if(t<=fall)z=p.z+v.z*t-325*t*t;
  else {float bounce=.6f*(650*fall-v.z),dt=t-fall;z=94+bounce*dt-325*dt*dt;}
  z=std::max(94.f,z);
 }
 float ex=std::max(0.f,std::abs(x)-790.f)/450.f,ez=std::max(0.f,z-540.f)/350.f;
 return std::clamp(speed/2300.f,0.f,1.f)*std::exp(-ex*ex-ez*ez);
}
struct MoveFrame {Vec pos,vel,forward,up;bool ground=false,jumped=false,flipping=false;};
inline MoveFrame move_frame(const CarState&s){return {s.pos,s.vel,s.rotMat.forward,s.rotMat.up,s.isOnGround,s.hasJumped,s.isFlipping};}
struct MoveReward {float launch=0,flip=0,recovery=0;};
struct MoveTrace {
 MoveFrame prev;bool valid=false,recovering=false,backflipped=false;Vec startForward;int started=0,lastLaunch=-100000,lastFlip=-100000,lastRecovery=-100000;
 void reset(const MoveFrame&f){prev=f;valid=true;recovering=backflipped=false;lastLaunch=lastFlip=lastRecovery=-100000;}
 MoveReward update(const MoveFrame&f,Vec ball,int tick){
  MoveReward r;if(!valid){reset(f);return r;}Vec to=ball-f.pos;float dist=to.Length();Vec dir=to.Normalized(),flat=to.To2D().Normalized();
  bool jump=!prev.jumped&&f.jumped&&(prev.ground||prev.pos.z<35);
  if(jump){
   if(ball.z>150&&ball.z<900&&dist<950&&f.forward.Dot(dir)>.25f&&f.vel.Dot(dir)>0&&tick-lastLaunch>=240){r.launch=.025f;lastLaunch=tick;}
   if(prev.vel.Dot(prev.forward)<-400&&prev.vel.Dot(flat)>250&&prev.forward.Dot(flat)<-.5f&&dist>900&&tick-lastRecovery>=480){recovering=true;backflipped=false;startForward=prev.forward;started=tick;}
  }
  if(f.flipping&&!prev.flipping){
   Vec dv=f.vel-prev.vel;float gain=dv.Dot(flat);
   if(gain>150&&dist>300&&f.forward.Dot(flat)>.3f&&tick-lastFlip>=360){r.flip=.12f*std::clamp(gain/500.f,0.f,1.f);lastFlip=tick;}
   if(recovering&&dv.Dot(startForward)<-100)backflipped=true;
  }
  if(recovering){int age=tick-started;
   if(age>300)recovering=false;
   else if(age>=18&&backflipped&&f.ground&&f.up.z>.8f&&f.forward.Dot(startForward)<-.7f&&f.forward.Dot(flat)>.7f&&f.vel.Dot(flat)>250){r.recovery=.3f;recovering=false;lastRecovery=tick;}
  }
  prev=f;return r;
 }
};
inline float bsafe_air(const CarState&c,const BallState&b,float dt){
 Vec d=b.pos-c.pos;float dist=d.Length();
 if(c.isDemoed||c.isOnGround||b.pos.z<180||c.pos.z<80||dist>1200)return 0;
 return .15f*dt*std::clamp(c.vel.Dot(d.Normalized())/2300.f,0.f,1.f);
}
