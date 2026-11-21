#define _GNU_SOURCE
#include <dlfcn.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
/* Process-local endpoint adapter: XRCE Agent 3.0.2 CLI offers no bind-address
 * option. Only its selected UDP port changes from ANY to loopback. No packet,
 * middleware or protocol data is inspected. System libraries remain untouched. */
int bind(int fd,const struct sockaddr *address,socklen_t length)
{
 static int (*real_bind)(int,const struct sockaddr *,socklen_t);
 if(!real_bind){void *symbol=dlsym(RTLD_NEXT,"bind");memcpy(&real_bind,&symbol,sizeof real_bind);}
 if(!real_bind){errno=ENOSYS;return -1;}
 const char *port=getenv("VEL_AGENT_UDP_PORT");
 if(port && address && address->sa_family==AF_INET && length>=sizeof(struct sockaddr_in)){
  struct sockaddr_in local;memcpy(&local,address,sizeof local);
  int kind=0;socklen_t size=sizeof kind;
  if(ntohs(local.sin_port)==(unsigned)strtoul(port,NULL,10) && local.sin_addr.s_addr==htonl(INADDR_ANY) && getsockopt(fd,SOL_SOCKET,SO_TYPE,&kind,&size)==0 && kind==SOCK_DGRAM){
   local.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
   int result=real_bind(fd,(const struct sockaddr *)&local,sizeof local);
   if(result==0){fputs("VEL_AGENT_LOOPBACK_BOUND\n",stdout);fflush(stdout);}
   return result;
  }
 }
 return real_bind(fd,address,length);
}
