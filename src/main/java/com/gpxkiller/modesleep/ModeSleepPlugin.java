package com.gpxkiller.modesleep;

import com.google.gson.*;
import com.google.inject.Inject;
import com.velocitypowered.api.event.Subscribe;
import com.velocitypowered.api.event.connection.DisconnectEvent;
import com.velocitypowered.api.event.player.ServerPreConnectEvent;
import com.velocitypowered.api.event.player.ServerPostConnectEvent;
import com.velocitypowered.api.event.proxy.ProxyInitializeEvent;
import com.velocitypowered.api.event.proxy.ProxyShutdownEvent;
import com.velocitypowered.api.plugin.Plugin;
import com.velocitypowered.api.plugin.annotation.DataDirectory;
import com.velocitypowered.api.proxy.*;
import com.velocitypowered.api.proxy.server.RegisteredServer;
import com.velocitypowered.api.scheduler.ScheduledTask;
import net.kyori.adventure.text.Component;
import org.slf4j.Logger;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;

@Plugin(id="minecraftmodesleep",name="MinecraftModeSleep",version="0.1.1",authors={"Gpxkiller"},description="Safe single-host backend sleep and wake")
public final class ModeSleepPlugin {
 private final ProxyServer proxy;private final Logger log;private final Path folder;
 private final Gson gson=new Gson();private final JoinQueue queue=new JoinQueue();
 private Path root;private String lobby;private Map<String,String> modes=Map.of();private volatile boolean enabled;
 private ScheduledTask task;private long warning=System.nanoTime()-60_000_000_000L;
 @Inject public ModeSleepPlugin(ProxyServer proxy,Logger log,@DataDirectory Path folder){this.proxy=proxy;this.log=log;this.folder=folder;}
 @Subscribe public void initialize(ProxyInitializeEvent event){
  try{
   Files.createDirectories(folder);Path config=folder.resolve("config.json");
   if(!Files.exists(config))try(var in=getClass().getResourceAsStream("/config.example.json")){Files.copy(Objects.requireNonNull(in),config);}
   var json=read(config,65536);enabled=json.get("enabled").getAsBoolean();
   if(!enabled){log.info("ModeSleep disabled. Configure the local worker before enabling.");return;}
   root=safe(Path.of(json.get("ipcRoot").getAsString()));if(!root.isAbsolute()||root.getNameCount()<3)throw new IOException("Dedicated IPC root required");
   lobby=proxy.getServer(json.get("lobby").getAsString()).orElseThrow(()->new IOException("Lobby is not registered")).getServerInfo().getName();
   var map=new LinkedHashMap<String,String>();var backends=new HashSet<String>();
   for(var e:json.getAsJsonObject("modes").entrySet()){
    String id=e.getKey(),name=e.getValue().getAsString();
    if(!id.matches("[a-z][a-z0-9-]{0,39}")||id.equals("lobby")||id.equals("proxy")||name.equals(lobby)||!backends.add(name))throw new IOException("Invalid mode mapping");
    var server=proxy.getServer(name).orElseThrow(()->new IOException("Mode not registered"));
    if(!server.getServerInfo().getAddress().getHostString().equals("127.0.0.1"))throw new IOException("Loopback IPv4 backends required");
    if(server.getServerInfo().getAddress().getPort()==proxy.getServer(lobby).orElseThrow().getServerInfo().getAddress().getPort())throw new IOException("Lobby port cannot be managed");
    map.put(id,server.getServerInfo().getName());
   }
   if(map.isEmpty()||map.size()>64)throw new IOException("Invalid mode count");modes=Map.copyOf(map);
   task=proxy.getScheduler().buildTask(this,this::tick).repeat(Duration.ofSeconds(1)).schedule();
   log.info("ModeSleep enabled; configured backends only, lobby never suspended.");
  }catch(Exception e){enabled=false;log.error("ModeSleep disabled: invalid configuration or inaccessible IPC. No service changed.");}
 }
 static Path safe(Path path)throws IOException{
  for(Path p=path.toAbsolutePath();p!=null;p=p.getParent())if(Files.isSymbolicLink(p))throw new IOException("Linked path refused");
  return path;
 }
 static JsonObject read(Path path,int limit)throws IOException{
  try(var in=Files.newInputStream(safe(path),LinkOption.NOFOLLOW_LINKS)){
   byte[] bytes=in.readNBytes(limit+1);if(bytes.length>limit)throw new IOException("IPC file too large");
   return JsonParser.parseString(new String(bytes,StandardCharsets.UTF_8)).getAsJsonObject();
  }catch(RuntimeException e){throw new IOException("Invalid IPC data");}
 }
 private static void atomic(Path path,String text)throws IOException{
  safe(path);Path temp=Files.createTempFile(path.getParent(),".proxy-",".tmp");
  try{Files.writeString(temp,text);Files.move(temp,path,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);}finally{Files.deleteIfExists(temp);}
 }
 private String id(RegisteredServer server){return modes.entrySet().stream().filter(e->e.getValue().equals(server.getServerInfo().getName())).map(Map.Entry::getKey).findFirst().orElse(null);}
 private JsonObject state()throws IOException{
  var status=read(root.resolve("public/status.json"),65536);
  double stamp=status.get("generatedAt").getAsDouble(),now=System.currentTimeMillis()/1000.0;
  if(!Double.isFinite(stamp)||now-stamp>30||stamp-now>5||status.get("version").getAsInt()!=1||!status.get("enabled").getAsBoolean())throw new IOException("Worker not ready");
  return status.getAsJsonObject("modes");
 }
 private JsonObject row(JsonObject state,String mode)throws IOException{
  var row=state.getAsJsonObject(mode);var server=proxy.getServer(modes.get(mode)).orElseThrow(()->new IOException("Server removed"));
  if(row==null||row.get("port").getAsInt()!=server.getServerInfo().getAddress().getPort())throw new IOException("Worker/proxy port mismatch");return row;
 }
 private void wake(String id)throws IOException{
  requestWake(root.resolve("inbox/"+id+".wake"));
 }
 static void requestWake(Path request)throws IOException{atomic(request,"wake\n");}
 @Subscribe public synchronized void beforeConnect(ServerPreConnectEvent event){
  if(!enabled)return;
  Player player=event.getPlayer();String mode=id(event.getOriginalServer());
  var dispatched=mode==null?null:queue.dispatched(player.getUniqueId(),mode);
  if(dispatched!=null){
   String source=player.getCurrentServer().map(s->s.getServerInfo().getName()).orElse(lobby);
   if(!queue.current(dispatched,player,source,System.nanoTime())){event.setResult(ServerPreConnectEvent.ServerResult.denied());return;}
  }else queue.cancel(player.getUniqueId());
  if(mode==null)return;
  try{
   var row=row(state(),mode);String phase=row.get("phase").getAsString();
   if(row.get("closed").getAsBoolean()){deny(event,"Ce mode est fermé.");return;}
   if(phase.equals("running"))return;
   if(!Set.of("sleeping","starting","stopping").contains(phase)){deny(event,"Ce mode est momentanément indisponible.");return;}
   String source=player.getCurrentServer().map(s->s.getServerInfo().getName()).orElse(lobby);
   queue.begin(player.getUniqueId(),player,source,mode,System.nanoTime());wake(mode);
   deny(event,"Le mode se réveille. Tu vas le rejoindre automatiquement.");
  }catch(Exception e){queue.cancel(player.getUniqueId());deny(event,"Le mode est momentanément indisponible. Réessaie plus tard.");}
 }
 private void deny(ServerPreConnectEvent event,String message){
  event.getPlayer().sendMessage(Component.text(message));
  if(event.getPlayer().getCurrentServer().isPresent())event.setResult(ServerPreConnectEvent.ServerResult.denied());
  else proxy.getServer(lobby).ifPresentOrElse(s->event.setResult(ServerPreConnectEvent.ServerResult.allowed(s)),()->event.setResult(ServerPreConnectEvent.ServerResult.denied()));
 }
 @Subscribe public void disconnected(DisconnectEvent event){queue.cancel(event.getPlayer().getUniqueId(),event.getPlayer());}
 @Subscribe public void connected(ServerPostConnectEvent event){
  var player=event.getPlayer();String source=player.getCurrentServer().map(s->s.getServerInfo().getName()).orElse("");
  for(var t:queue.snapshot())if(t.id().equals(player.getUniqueId())&&t.session()==player&&!queue.current(t,player,source,System.nanoTime()))queue.remove(t);
 }
 private synchronized void tick(){
  if(!enabled)return;
  try{
   var counts=new LinkedHashMap<String,Integer>();for(var e:modes.entrySet())counts.put(e.getKey(),proxy.getServer(e.getValue()).orElseThrow().getPlayersConnected().size());
   atomic(root.resolve("inbox/heartbeat.json"),gson.toJson(Map.of("generatedAt",System.currentTimeMillis()/1000.0,"counts",counts)));
   var states=state();
   for(var ticket:queue.snapshot()){
    var player=proxy.getPlayer(ticket.id()).orElse(null);
    if(player==null||!player.isActive()||!queue.current(ticket,player,player.getCurrentServer().map(s->s.getServerInfo().getName()).orElse(lobby),System.nanoTime())){
     if(queue.remove(ticket)&&player!=null&&player.isActive()&&queue.expired(ticket,System.nanoTime()))player.sendMessage(Component.text("Le réveil prend trop de temps. Réessaie de rejoindre le mode."));
     continue;
    }
    if(player.getCurrentServer().isEmpty())continue;
    var row=row(states,ticket.target());
    if(row.get("closed").getAsBoolean()||row.get("phase").getAsString().equals("unavailable")){if(queue.remove(ticket))player.sendMessage(Component.text("Ce mode est indisponible. Réessaie plus tard."));continue;}
    if(!row.get("phase").getAsString().equals("running"))continue;
    var server=proxy.getServer(modes.get(ticket.target())).orElseThrow();
    if(queue.dispatch(ticket))player.createConnectionRequest(server).connect().whenComplete((result,error)->{
     queue.finished(ticket);
     if((error!=null||!result.isSuccessful())&&player.isActive())player.sendMessage(Component.text("Connexion impossible. Tu restes sur ton serveur actuel."));
    });
   }
  }catch(Exception e){
   if(System.nanoTime()-warning>60_000_000_000L){warning=System.nanoTime();log.warn("ModeSleep worker/IPC unavailable; no server is assumed empty or ready.");}
   // Expire tickets even while IPC is unavailable; never retain an unbounded queue.
   for(var t:queue.snapshot())if(queue.expired(t,System.nanoTime()))queue.remove(t);
  }
 }
 @Subscribe public void shutdown(ProxyShutdownEvent event){enabled=false;if(task!=null)task.cancel();queue.clear();}
}
