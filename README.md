# 自驾路书制作

把一次自驾旅行整理成一本能带上路的路书。告诉 AI 去哪儿、玩几天、怎么出发、和谁同行，它会先和你确认每天的路线与过夜地，再查资料、画地图、编排成书。

## 路书里有什么

- **每日行程**：当天的路线、预计里程、景点顺序、停车提示和过夜地。
- **出行资料**：整理门票、开放时间和车程，标明数据来源与核验日期。
- **路线图和景点地图**：用 SVG 绘制每天怎么开、景点在哪，放大后仍然清晰。
- **两种交付方式**：生成自带地图的单文件 `book.html`，可在浏览器打开并按 A4 打印。也可以发布为飞书云文档，方便同行的人一起看和修改。

## 安装到 WorkBuddy

1. 在本仓库点 **Code → Download ZIP**，解压后将文件夹命名为 `roadbook-maker`。
2. 把文件夹放到 `~/.workbuddy/skills/`。Windows 上可以在资源管理器地址栏输入 `%USERPROFILE%\.workbuddy\skills`。放好后，`SKILL.md` 应直接位于 `roadbook-maker` 文件夹内。
3. 新开一个 WorkBuddy 对话，发出你的路书需求。

本地构建使用 Python 3.11 或更新版本。将 SVG 渲染成 PNG 需要 Playwright 和浏览器，发布飞书还需要已登录的 `lark-cli`。

## 试着这样说

> 帮我做一本川西小环线 5 天自驾路书。成都落地租车，两位大人和一个孩子。先给我每天去哪、开多少公里、住哪里的安排。我确认路线后，再查门票和开放时间，画上地图，做成可打印的路书。

## 手动构建

在仓库根目录运行下面的命令初始化书稿。编辑 `book.toml` 和各章正文，准备好配图后，再运行后两条命令检查并生成 HTML。

```bash
python scripts/roadbook.py init ../my-roadbook --title "我的自驾路书"
python scripts/roadbook.py doctor ../my-roadbook
python scripts/roadbook.py build ../my-roadbook
```

安装细节、章节模板和飞书发布方法见 [详细使用说明](README-怎么用.md)。完整的路书制作流程见 [SKILL.md](SKILL.md)。
