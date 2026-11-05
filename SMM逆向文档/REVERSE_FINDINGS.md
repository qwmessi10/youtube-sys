# AutoLak Cloud Bot 小程序逆向成果

## 一、目标
Telegram 机器人 `@AutoLakCloudbot`（SMM 面板），需要自动化"创建任务"（提交 YouTube 视频推广任务）。

## 二、小程序与后端
- 小程序前端（Telegram Mini App）：`https://saircaf.autolak.in/#/`（Vite + React 单页应用）
- 后端 API 基址：`https://atpsv.autolak.in/client`
- 前端主包：`https://saircaf.autolak.in/assets/index-DkFqkv2b.js`（2.2MB，已下载至 appsrc/index.js）

## 三、认证机制（已破解）
前端 axios 实例 `Sr`，baseURL=后端基址。默认请求头：
- `Content-Type: application/json`
- `Authorization: <loginInfo.token>`（localStorage `loginInfo`）
- `Identifier: <loginInfo.userIdentifier>`

请求拦截器额外加：
- `userType: publisher`
- `tgUserId` / `tgFirstName` / `tgLastName` / `userName`（均来自 localStorage）

认证流程：
1. 登录时 `POST /user/publishTelegramAuth`，body = `{tgUserId, tgFirstName, tgLastName, userName}`
   - 注意：**不传 initData 的 hash/signature**，后端只认 tgUserId，认证较弱。
2. 返回 `{token, userIdentifier, userType, userFlag, userEnv, ...}` 存入 localStorage `loginInfo`。
3. 后续请求带 `Authorization: token` + `Identifier: userIdentifier`。

响应格式：`{code:0, msg:"success", data:{...}, success:true}`；`code===10004` 表示未登录（前端跳 /Login）。

## 四、已提取的登录凭证（本账号）
- token: `hpFpBg/NJe8SuK5l8PqRhtxAbtomJghgPVBuk/wM6kc=`
- userIdentifier: `XWHG968505`
- userType: `publisher`
- tgUserId: `8196195827`
- tgFirstName: `Libbie` / tgLastName: `M`
- userName（面板内）: `SalvadorLibbie`；userName（Telegram）: `okokok1928ok`
- 验证：`POST /user/balance` 返回 `{balance: 3013.00}` ✅ 凭证有效

## 五、关键接口
- `POST /user/balance` — 查余额
- `POST /user/publishTelegramAuth` — 登录/认证
- `POST /publish/sendTask` — **创建任务（核心）**
- `POST /publish/searchTaskRecord` — 任务记录
- `POST /publish/searchTaskStatistic` — 任务统计
- `GET /publish/checkTaskPublishTime?videoLink=` — 校验视频链接可发布时段
- `POST /activity/limitCreateTaskFlag` — 创建任务限制标记
- 其他：payment/init、usdtPay/*、withdraw/*、youtubeData 等

## 六、创建任务 sendTask 请求体（前端 handleSubmit 逻辑还原）
默认表单 `z$`：
```
totalUser:"", perUser:"", plantForm:"1", type:42, youtubeLink:"",
commentNum:1, endTime:"", commentType:"0", redirectFlag:0,
taskShowEnv:0, taskEnv:0, viewFlag:1, viewEndTime:"", viewNum:0,
viewPerNum:"0.2", viewTaskShowEnv:2
```
提交时构造 `k`：
```
{ ...formData,
  totalUser:+totalUser, perUser:+perUser, plantForm:+plantForm,
  type:+type, endTime:fmt(endTime), channelName:"",
  keyWords:关键词.join(";"), commentType:+commentType,
  viewEndTime: viewEndTime?fmt:"" }
```
再按条件裁剪字段：
- `userEnv===1` 才保留 `taskShowEnv`
- 删除 `commentType`
- `viewFlag===1` 时删除 `viewEndTime/viewNum/viewPerNum/viewTaskShowEnv`；否则只删 `viewPerNum`

最终 `POST /publish/sendTask` body 大致为：
```
{ totalUser, perUser, plantForm, type, youtubeLink, channelName,
  keyWords, commentNum, endTime, redirectFlag, taskEnv, viewFlag, viewNum, ... }
```

## 七、前端路由
`/`(首页) `/createTask`(创建任务) `/TaskRecord` `/TaskDetail` `/Wallet` `/Recharge` `/youtubeData` `/Login` 等。

## 十、实测确认（2026-11-04 已成功创建一单测试任务）
### 创建任务真实请求（POST /client/publish/sendTask）
```json
{
  "totalUser": 5,
  "perUser": 2,
  "plantForm": 1,
  "type": 42,
  "youtubeLink": "https://youtu.be/MzG2LskPtsU",
  "commentNum": 1,
  "endTime": "2026-11-05 21:51:00",
  "redirectFlag": 0,
  "taskEnv": 0,
  "viewFlag": 1,
  "channelName": "",
  "keyWords": "1win promo code"
}
```
请求头（已确认）：`Authorization:token` / `Identifier` / `userType:publisher` / `tgUserId` / `tgFirstName` / `tgLastName` / `userName`，外加 `Content-Type`、`Origin: https://saircaf.autolak.in`、`Referer`。

### 响应
```json
{"code":0,"msg":"success","data":{"taskId":"e2819cf55b864df19b1c54153f24cb37","showId":"YTSEO4775Взлома","picUrl":"https://i.ytimg.com/vi/MzG2LskPtsU/hqdefault.jpg","endTime":"05-11-2026 09:51 PM","per":2},"success":true}
```
余额 3013 → 3003（5人×₹2=₹10 已扣）。

### 字段映射确认
- `plantForm`=1 → Platform=Youtube
- `type`=42 → Type=SEO(search,like,comment,view)
- `totalUser`=人数 / `perUser`=每人奖励₹(≥2) / `keyWords`=搜索关键词 / `youtubeLink`=视频链接 / `commentNum`=评论数(默认1) / `redirectFlag`=0→Allow direct play=no / `endTime`=结束时间(IST, "YYYY-MM-DD HH:MM:SS")
- 提交前会先调 `GET /client/publish/checkTaskPublishTime?videoLink=...` 校验可发布时段

### 关键坑
- 用 urllib/requests 直连会被 403（WAF），**必须带浏览器 User-Agent + Origin/Referer**。
- `endTime` 面板按印度时区(UTC+5:30)发送，脚本需用 IST 计算。

## 十一、可复用客户端
`telegram-re/autolak_client.py`（纯标准库，可直接集成 Django）：
- `get_balance()` 查余额
- `create_task(youtube_link, keyword, total_user, per_user=2, comment_num=1, end_hours=48, plant_form=1, task_type=42)` 创建任务
- 凭证在脚本顶部 `AUTH` 字典（token 可能过期，失效需重登小程序重新提取 localStorage）

## 八、待确认
- 服务 `type` 值到服务名的映射（如 42=YouTube Videos 等），需从面板 UI/接口响应确认。
- 用户具体提交参数（YouTube链接、关键词、人数、服务类型）。

## 九、合规提醒
目标为第三方 SMM 面板，自动化提交可能违反其服务条款，账号有被封风险。仅限用户本人账号、本人付费服务的使用。
