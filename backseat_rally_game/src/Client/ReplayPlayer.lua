local root=game:GetService('ReplicatedStorage'):WaitForChild('BackseatExpedition')
local Codec=require(root.Shared.Replay)
local Player={};Player.__index=Player
function Player.new(remote,metadata)
 return setmetatable({remote=remote,meta=metadata,cache={},pending={},queue={},alive=true,errors={}},Player)
end
function Player:page(index)
 if not self.meta.pages[index]or self.cache[index]or self.pending[index]then return end
 self.pending[index]=true;self.queue[#self.queue+1]=index
 if self.worker then return end;self.worker=true
 task.spawn(function()
  while self.alive and #self.queue>0 do
   local i=table.remove(self.queue,1);local result
   for attempt=1,3 do
    local ok,response=pcall(function()return self.remote:InvokeServer('page',{id=self.meta.id,index=i})end)
    if ok and response and response.text then
     local decoded,frames=pcall(Codec.decode,response.text)
     if decoded then result=frames;break else self.errors[i]='Invalid replay data'end
    else self.errors[i]=ok and response and response.error or 'Connection interrupted'end
    task.wait(.5*attempt)
   end
   if not self.alive then break end
   self.cache[i]=result;self.pending[i]=nil
   if result then self.errors[i]=nil end
   -- A five-page moving cache bounds both ghost and replay memory.
   for j in pairs(self.cache)do if math.abs(j-(self.current or i))>2 then self.cache[j]=nil end end
   task.wait(.18)
  end
  self.worker=false
 end)
end
function Player:sample(t)
 local pages=self.meta.pages;local index=1
 for i,p in ipairs(pages)do if p.from<=t then index=i else break end end
 self.current=index;self:page(index);self:page(index+1)
 local frames=self.cache[index]
 if not frames then return nil,self.errors[index]or 'Loading replay…'end
 if frames[#frames][1]<t*1000 and self.cache[index+1]then
  local joined=table.clone(frames);joined[#joined+1]=self.cache[index+1][1];return Codec.sample(joined,t)
 end
 return Codec.sample(frames,t)
end
function Player:destroy()self.alive=false;self.queue={};self.cache={}end
return Player
