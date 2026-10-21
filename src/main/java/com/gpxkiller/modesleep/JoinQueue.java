package com.gpxkiller.modesleep;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/** Session identity, not just UUID: an old login must never move a new one. */
public final class JoinQueue {
 public record Ticket(UUID id,Object session,String source,String target,long deadline){}
 private final Map<UUID,Ticket> pending=new ConcurrentHashMap<>();
 private final Map<UUID,Ticket> dispatching=new ConcurrentHashMap<>();
 public synchronized Ticket begin(UUID id,Object session,String source,String target,long now){
  if(!pending.containsKey(id)&&pending.size()>=1000)throw new IllegalStateException("Waiting queue full");
  var ticket=new Ticket(id,session,source,target,now+180_000_000_000L);pending.put(id,ticket);return ticket;
 }
 public Collection<Ticket> snapshot(){return List.copyOf(pending.values());}
 public boolean expired(Ticket t,long now){return now-t.deadline()>=0;}
 public boolean current(Ticket t,Object session,String source,long now){return pending.get(t.id())==t&&t.session()==session&&Objects.equals(t.source(),source)&&!expired(t,now);}
 public boolean remove(Ticket t){return pending.remove(t.id(),t);}
 public synchronized boolean dispatch(Ticket t){return pending.get(t.id())==t&&dispatching.size()<1000&&dispatching.putIfAbsent(t.id(),t)==null;}
 public Ticket dispatched(UUID id,String target){var t=dispatching.get(id);return t!=null&&t.target().equals(target)?t:null;}
 public void finished(Ticket t){dispatching.remove(t.id(),t);pending.remove(t.id(),t);}
 public void cancel(UUID id){pending.remove(id);}
 public void cancel(UUID id,Object session){pending.computeIfPresent(id,(key,t)->t.session()==session?null:t);}
 public int size(){return pending.size();}
 public void clear(){pending.clear();dispatching.clear();}
}
