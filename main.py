from astrbot.api.all import *
import re
import os
import json
import aiohttp
from astrbot.api.all import Star, Context, register
from astrbot.api.event import CommandResult, AstrMessageEvent
from bilibili_api import Credential, video
from astrbot.api.message_components import Image, Plain
from astrbot.api.event.filter import command
from bilibili_api.bangumi import IndexFilter as IFg
from typing import Any, Dict
from bilibili_api.exceptions import ApiException
from aiohttp import ClientSession
from tqdm.asyncio import tqdm
from astrbot.api.message_components import Video
import logging
logger = logging.getLogger(__name__)



BV = r"(?:\?.*)?(?:https?:\/\/)?(?:www\.)?bilibili\.com\/video\/(BV[\w\d]+)\/?(?:\?.*)?|BV[\w\d]+"
b23 = r"(https?://(?:b23\.tv|bili2233\.cn)/[A-Za-z\d._?%&+\-=\/#]+)"

BILIBILI_HEADER = {
    'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 '
        'Safari/537.36',
    'referer': 'https://www.bilibili.com',
}





@register("bilibili_plus", "rikka", "bilibili的视频解析", "1.1.0")
class BiliToolboxPlugin(Star):

    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.SESSDATA = self.config["sessdata"]
        self.BILI_JCT = self.config["bili_jct"]
        self.BUVID3 = self.config["buvid3"]
        self.BUVID4 = self.config["buvid4"]
        self.DDEUSERID = self.config["dedeuserid"]
        self.AC_TIME_VALUE = self.config["ac_time_value"]
        self.FFMPEG_PATH = self.config["ffmpeg_path"]

        if not all([self.SESSDATA, self.BILI_JCT, self.BUVID3]):
            logger.warning("未设置SESSDATA, BILI_JCT, BUVID3, 部分功能将无法使用")
            return
                     
    async def get_video_info(self, bili_url: str):
        if len(bili_url) == 12:
            bvid = bili_url
        else:
            match_ = re.search(BV, bili_url, re.IGNORECASE)
            if not match_:
                return
            bvid = "BV" + match_.group(1)[2:]

        try:
            credential = Credential(sessdata=None) 
            v = video.Video(bvid=bvid, credential=credential)
            info = await v.get_info()
            online = await v.get_online()
            ret = f"""Billibili 视频信息：
标题: {info['title']}
UP主: {info['owner']['name']}
播放量: {info['stat']['view']}
点赞: {info['stat']['like']}
投币: {info['stat']['coin']}
总共 {online['total']} 人正在观看"""
            ls = [Plain(ret), Image.fromURL(info["pic"])]

            result = CommandResult()
            result.chain = ls
            result.use_t2i(False)
            return result
        except Exception as e:
            logger.error(f"获取视频信息失败: {e}")
            return CommandResult(plain_text=f"获取视频信息失败: {e}")
            
            
    async def bili_video(self, bili_url: str):
        """解析bili小程序"""
        bili_rex = r"(https?://(?:b23\.tv|bili2233\.cn)/[A-Za-z\d._?%&+\-=\/#]+)"
        if "b23.tv" in bili_url or "bili2233.cn" in bili_url or "QQ小程序" in bili_url:
            b_s_e = re.search(bili_rex, bili_url.replace(" \\", ""))[0]
            ssl_context = aiohttp.TCPConnector(verify_ssl=False)
            async with aiohttp.ClientSession(headers=BILIBILI_HEADER, connector=ssl_context) as session:
                try:
                    async with session.get(b_s_e) as response:
                        data = response.url
                        code = response.status
                        if code == 200:
                            bili_url = data
                            # 显式关闭响应
                            await response.release()
                            return await self.get_video_info(str(bili_url))
                        else:
                            logger.error(f"错误: {code}")
                            return f"错误: {code}"
                except Exception as e:
                    logger.error(f"错误: {e}")
                    # 显式关闭连接器
                    await ssl_context.close()
                    return f"错误: {e}"
                finally:
            # 确保连接关闭
                    await session.close()    
        


    @event_message_type(EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """监听所有消息事件"""
        
        bili = event.message_obj.message
        event_str = event.message_str
        for component in bili:
            if isinstance(component, Json):
                try:
                    bilidata = json.loads(component.data) # 尝试解析json字符串
                    
                    # 检查是否为 QQ 哔哩哔哩小程序视频
                    if bilidata.get("app") == "com.tencent.miniapp_01" and bilidata.get("meta") and bilidata.get("meta").get("detail_1"):
                        detail_1 = bilidata["meta"]["detail_1"]
                        qqdocurl = detail_1.get("qqdocurl")
                        logger.info(f"检测到bili小程序：{qqdocurl}")
                        yield await self.bili_video(qqdocurl) 
                    else:
                        logger.info(f"非哔哩哔哩链接: {component.data}")

                except json.JSONDecodeError:
                    logger.error(f"JSON 解析错误: {component.data}")

                except Exception as e:
                    logger.error(f"on_message函数发生错误：{e}")

            # 匹配纯文本消息,是否包含bilibili链接,并格式化为纯BV号
            for match in re.findall(BV, event_str): 
                if len(event_str) == 12:
                    bili_url = event_str
                    logger.info(f"检测到BV号: {event_str}")
                    yield await self.get_video_info(bili_url)
                else:
                    match_ = re.search(BV, event_str, re.IGNORECASE)
                    if not match_:
                        return
                    
                logger.info(f"检测到BV号: {match}")
                yield await self.get_video_info(match)
                return
            # 处理bili短链
            for match in re.findall(b23, event_str): 
                if "b23.tv" in match or "bili2233.cn" in match or "QQ小程序" in match:
                    logger.info(f"检测到bili短链接: {match}")
                yield await self.bili_video(event_str)
                return
