#pragma once
// A chain is paid only at a real goal. Repeating/alternating known events adds
// nothing. Opponent contact, ambiguous contact, or age >8s clears the chain.
struct ComboTrace {
 int owner=-1,mask=0,start=0;
 void reset(){owner=-1;mask=0;start=0;}
 void touch(int bits,int tick){
  if(bits==3){reset();return;}
  if(bits==1||bits==2){int t=bits==1?0:1;if(owner!=t||tick-start>960){owner=t;mask=0;start=tick;}mask|=1;}
 }
 void event(int team,int bits,int tick){if(owner==team&&tick-start<=960)mask|=bits;}
 float goal(int team,int tick)const{if(owner!=team||tick-start>960)return 0;int n=0;for(int b=2;b<=8;b*=2)if(mask&b)n++;return .5f*n;}
};
