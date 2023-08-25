import os, sys, json, yaml
sys.path.append(os.path.realpath('../lib'))
from messaging import RedisMessaging
from diameter import Diameter
from banners import Banners
from logtool import LogTool

class HssService:
    
    def __init__(self, redisHost: str='127.0.0.1', redisPort: int=6379):

        try:
            with open("../config.yaml", "r") as self.configFile:
                self.config = yaml.safe_load(self.configFile)
        except:
            print(f"[HSS] Fatal Error - config.yaml not found, exiting.")
            quit()
        self.redisMessaging = RedisMessaging(host=redisHost, port=redisPort)
        self.logTool = LogTool(config=self.config)
        self.banners = Banners()
        self.mnc = self.config.get('hss', {}).get('MNC', '999')
        self.mcc = self.config.get('hss', {}).get('MCC', '999')
        self.originRealm = self.config.get('hss', {}).get('OriginRealm', f'mnc{self.mnc}.mcc{self.mcc}.3gppnetwork.org')
        self.originHost = self.config.get('hss', {}).get('OriginHost', f'hss01')
        self.productName = self.config.get('hss', {}).get('ProductName', f'PyHSS')
        self.diameterLibrary = Diameter(originHost=self.originHost, originRealm=self.originRealm, productName=self.productName, mcc=self.mcc, mnc=self.mnc)
        self.logTool.log(service='HSS', level='info', message=f"{self.banners.hssService()}", redisClient=self.redisMessaging)

    def handleQueue(self):
        """
        Gets and parses inbound diameter requests, processes them and queues the response.
        """
        while True:
            try:
                inboundQueue = self.redisMessaging.getNextQueue(pattern='diameter-inbound*')
                inboundMessage = self.redisMessaging.getMessage(queue=inboundQueue)
                assert(len(inboundMessage))

                inboundDict = json.loads(inboundMessage)
                inboundBinary = bytes.fromhex(next(iter(inboundDict.values())))
                inboundSplit = str(inboundQueue).split('-')
                inboundHost = inboundSplit[2]
                inboundPort = inboundSplit[3]
                inboundTimestamp = inboundSplit[4]

                try:
                    diameterOutbound = self.diameterLibrary.generateDiameterResponse(binaryData=inboundBinary)
                    diameterMessageTypeDict = self.diameterLibrary.getDiameterMessageType(binaryData=inboundBinary)
                    diameterMessageTypeInbound = diameterMessageTypeDict.get('inbound', '')
                    diameterMessageTypeOutbound = diameterMessageTypeDict.get('outbound', '')
                except Exception as e:
                    self.hssLogger.warn(f"[HSS] [handleInboundQueue] Failed to generate diameter outbound: {e}")
                    continue

                self.logTool.log(service='HSS', level='debug', message=f"[HSS] [handleInboundQueue] [{diameterMessageTypeInbound}] Inbound Diameter Inbound Queue: {inboundQueue}", redisClient=self.redisMessaging)
                self.logTool.log(service='HSS', level='debug', message=f"[HSS] [handleInboundQueue] [{diameterMessageTypeInbound}] Inbound Diameter Inbound: {inboundMessage}", redisClient=self.redisMessaging)

                if not len(diameterOutbound) > 0:
                    continue
                
                outboundQueue = f"diameter-outbound-{inboundHost}-{inboundPort}-{inboundTimestamp}"
                outboundMessage = json.dumps({"diameter-outbound": diameterOutbound})

                self.logTool.log(service='HSS', level='debug', message=f"[HSS] [handleInboundQueue] [{diameterMessageTypeOutbound}] Generated Diameter Outbound: {diameterOutbound}", redisClient=self.redisMessaging)
                self.logTool.log(service='HSS', level='debug', message=f"[HSS] [handleInboundQueue] [{diameterMessageTypeOutbound}] Outbound Diameter Outbound Queue: {outboundQueue}", redisClient=self.redisMessaging)
                self.logTool.log(service='HSS', level='debug', message=f"[HSS] [handleInboundQueue] [{diameterMessageTypeOutbound}] Outbound Diameter Outbound: {outboundMessage}", redisClient=self.redisMessaging)

                self.redisMessaging.sendMessage(queue=outboundQueue, message=outboundMessage, queueExpiry=60)

            except Exception as e:
                continue
        


if __name__ == '__main__':
    hssService = HssService()
    hssService.handleQueue()