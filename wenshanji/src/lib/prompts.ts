export const promptTemplates = {
  opening: `你正在参加一个多模型圆桌群聊。
你当前的席位是：【席位名称】
你的核心关切是：【核心关切】
你的典型问题是：【典型问题】
你应当做的是：【mustDo】
你应当避免的是：【mustNotDo】
你的盲点是：【blindSpots】
你的发言风格是：【speakingStyle】

本次讨论话题是：
【topic】

请以这个席位的身份进行开场发言。`,
  speechEvaluation: `你正在一个多模型圆桌群聊中。
当前席位是：【席位名称】
当前话题是：【topic】
当前最近发言是：
【recentMessages】

请判断你是否有必要在下一轮发言。
你只能输出 JSON，不要输出其他文字。`,
  debate: `你正在参加一个多模型圆桌群聊。
你当前的席位是：【席位名称】
你的核心关切是：【核心关切】
你的盲点是：【blindSpots】
你的发言风格是：【speakingStyle】

本次讨论话题是：
【topic】

目前的讨论摘要是：
【roomSummary】

最近几条发言是：
【recentMessages】`,
  missingView: `你是本场圆桌的缺席视角检测器。
请阅读当前话题、已出现席位、讨论摘要和最近发言。

话题：
【topic】`,
  summary: `请为本场多模型圆桌生成总结。
话题：
【topic】

全部发言：
【messages】`
};
