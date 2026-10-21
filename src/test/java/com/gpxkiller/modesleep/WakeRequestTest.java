package com.gpxkiller.modesleep;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.nio.file.attribute.FileTime;
import static org.junit.jupiter.api.Assertions.*;
class WakeRequestTest {
 @TempDir Path directory;
 @Test void aNewArrivalRefreshesOneExpiredRequest()throws Exception{
  Path p=directory.resolve("arena.wake");Files.writeString(p,"old");Files.setLastModifiedTime(p,FileTime.fromMillis(1));
  ModeSleepPlugin.requestWake(p);
  assertEquals("wake\n",Files.readString(p));assertTrue(Files.getLastModifiedTime(p).toMillis()>1);
  for(int i=0;i<100;i++)ModeSleepPlugin.requestWake(p);
  try(var files=Files.list(directory)){assertEquals(1,files.count());}
 }
}
