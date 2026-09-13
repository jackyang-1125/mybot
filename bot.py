import datetime
import asyncio
import os
import threading
from flask import Flask, render_template_string
import discord
from discord import app_commands
from discord.ext import commands

# ==================== 1. 設置 Flask 網頁伺服器 ====================
app = Flask(__name__)

exams_data = []
EXCLUSIVE_CHANNEL_ID = 1548647622263181342
dashboard_message_id = None

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <title>班級互動式課表</title>
    <script src="https://internals-ssl.discord.com/sdk/v1/embedded-app-sdk.js"></script>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #313338; color: #dbdee1; padding: 20px; margin: 0; display: flex; flex-direction: column; align-items: center; }
        h2 { color: #fff; margin-bottom: 10px; }
        .table-container { width: 100%; max-width: 1100px; background: #2b2d31; padding: 15px; border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.4); overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; text-align: center; font-size: 14px; }
        th, td { border: 1px solid #3f4147; padding: 12px 8px; vertical-align: middle; }
        th { background: #1e1f22; color: #f2f3f5; }
        tr:nth-child(even) { background: #2b2d31; }
        tr:nth-child(odd) { background: #313338; }
        .schedule-cell { cursor: pointer; transition: background 0.2s; border-radius: 4px; }
        .schedule-cell:hover { background: #3f4147; color: #fff; }
        .empty { color: #80848e; }
        .sat-disabled { background: #232428 !important; color: #555; cursor: not-allowed; }

        /* Wordle 風格彈出視窗 (Modal) */
        .modal-overlay {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0, 0, 0, 0.7); display: flex; justify-content: center; align-items: center;
            opacity: 0; pointer-events: none; transition: opacity 0.25s ease-in-out; z-index: 1000;
        }
        .modal-overlay.active { opacity: 1; pointer-events: auto; }
        .modal-box {
            background: #313338; color: #dbdee1; padding: 24px; border-radius: 12px;
            width: 90%; max-width: 400px; box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            transform: scale(0.8); transition: transform 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            border: 1px solid #3f4147; text-align: center;
        }
        .modal-overlay.active .modal-box { transform: scale(1); }
        .modal-box h3 { margin-top: 0; color: #fff; font-size: 20px; border-bottom: 1px solid #3f4147; padding-bottom: 10px; }
        .modal-content { font-size: 16px; margin: 20px 0; line-height: 1.6; white-space: pre-wrap; background: #2b2d31; padding: 12px; border-radius: 6px; }
        .modal-close {
            background: #5865f2; color: white; border: none; padding: 10px 20px;
            font-size: 14px; border-radius: 6px; cursor: pointer; font-weight: bold; transition: background 0.2s;
        }
        .modal-close:hover { background: #4752c4; }
    </style>
</head>
<body>
    <h2>📅 班級互動式課表</h2>
    <div style="font-size: 13px; color: #949ba4; margin-bottom: 15px;">點擊任意課程格子即可彈出詳細資訊</div>
    
    <div class="table-container">
        <table>
            <thead>
                <tr>
                    <th>節次</th>
                    <th>時間</th>
                    <th>一</th>
                    <th>二</th>
                    <th>三</th>
                    <th>四</th>
                    <th>五</th>
                    <th>六</th>
                </tr>
            </thead>
            <tbody>
                {% for period_name, time_str in time_slots %}
                <tr>
                    <td><strong>{{ period_name }}</strong></td>
                    <td>{{ time_str }}</td>
                    {% for i in range(6) %}
                        {% if i == 5 and loop.index0 > 4 %}
                            <td class="sat-disabled">-</td>
                        {% else %}
                            {% set cell_data = namespace(text='', id='') %}
                            {% for item in exams_data %}
                                {% if item.period == period_name %}
                                    {% set cell_data.text = item.content %}
                                    {% set cell_data.id = item.id %}
                                {% endif %}
                            {% endfor %}
                            <td class="schedule-cell" onclick="openModal('{{ period_name }}', '{{ time_str }}', '{{ cell_data.text | replace('\\n', '<br>') | safe }}', '{{ cell_data.id }}')">
                                {% if cell_data.text %}
                                    {{ cell_data.text | safe }}
                                {% else %}
                                    <span class="empty">-</span>
                                {% endif %}
                            </td>
                        {% endif %}
                    {% endfor %}
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <div class="modal-overlay" id="modalOverlay" onclick="closeModal(event)">
        <div class="modal-box" onclick="event.stopPropagation()">
            <h3 id="modalTitle">課程詳細資訊</h3>
            <div class="modal-content" id="modalBody">無內容</div>
            <button class="modal-close" onclick="closeModalDirect()">關閉</button>
        </div>
    </div>

    <script>
        let discordSdk;
        window.addEventListener('DOMContentLoaded', async () => {
            if (window.DiscordSDK) {
                const clientId = "你的 Discord Client ID";
                discordSdk = new window.DiscordSDK(clientId);
                await discordSdk.ready();
            }
        });

        function openModal(period, time, content, id) {
            document.getElementById('modalTitle').innerText = period + " (" + time + ")";
            if(content.trim() === "") {
                document.getElementById('modalBody').innerHTML = "<span style='color: #80848e;'>目前無排程內容</span>";
            } else {
                document.getElementById('modalBody').innerHTML = content + (id ? "<br><br><span style='font-size:12px; color:#949ba4;'>項目 ID: #" + id + "</span>" : "");
            }
            document.getElementById('modalOverlay').classList.add('active');
        }
        function closeModal(e) {
            document.getElementById('modalOverlay').classList.remove('active');
        }
        function closeModalDirect() {
            document.getElementById('modalOverlay').classList.remove('active');
        }
    </script>
</body>
</html>
"""


@app.route("/")
def index():
  time_slots = [
      ("第0節早自修", "07:30 - 08:00"),
      ("第1節", "08:10 - 08:55"),
      ("第2節", "09:15 - 10:00"),
      ("第3節", "10:10 - 10:55"),
      ("第4節", "11:05 - 11:50"),
      ("第5節", "13:10 - 13:55"),
      ("第6節", "14:10 - 14:55"),
      ("第7節", "15:10 - 15:55"),
      ("第8節", "16:05 - 16:50"),
      ("第9節", "16:55 - 17:40"),
      ("第10節", "17:45 - 18:30"),
  ]
  return render_template_string(
      HTML_TEMPLATE, time_slots=time_slots, exams_data=exams_data
  )


def run_flask():
  port = int(os.environ.get("PORT", 10000))
  app.run(host="0.0.0.0", port=port)


# ==================== 2. Discord 機器人核心 ====================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
dashboard_message_id = None


@bot.event
async def on_ready():
  print(f"Discord 機器人已成功登入 --> {bot.user}")
  try:
    synced = await bot.tree.sync()
    print(f"已同步 {len(synced)} 個 Slash 指令")
  except Exception as e:
    print(e)


def create_dashboard_view():
  web_url = os.environ.get(
      "RENDER_External_URL", "https://mybot-v6cj.onrender.com"
  )
  view = discord.ui.View(timeout=None)
  view.add_item(
      discord.ui.Button(
          label="🌐 開啟互動課表",
          style=discord.ButtonStyle.link,
          url=web_url,
      )
  )
  return view


def create_dashboard_embed():
  now_taiwan = datetime.datetime.now(
      datetime.timezone(datetime.timedelta(hours=8))
  )
  embed = discord.Embed(
      title="📅 班級課表與時間總表",
      description=(
          "點擊下方按鈕即可開啟**互動式網頁課表**！\n\n➕ 新增指令：`/add_schedule`"
          " | 🗑️ 刪除指令：`/del_schedule` | 📅 檢視指令：`/檢視課表`"
      ),
      color=0x3498DB,
      timestamp=now_taiwan,
  )
  embed.set_footer(text="動態互動式 HTML 課表系統")
  return embed


async def update_or_create_dashboard(channel):
  global dashboard_message_id
  embed = create_dashboard_embed()
  view = create_dashboard_view()

  if dashboard_message_id:
    try:
      msg = await channel.fetch_message(dashboard_message_id)
      await msg.edit(embed=embed, view=view)
      return
    except discord.NotFound:
      pass

  msg = await channel.send(embed=embed, view=view)
  dashboard_message_id = msg.id


# 檢查是否為管理員 (版主) 的 Decorator
def is_admin():
  async def predicate(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
      await interaction.response.send_message(
          "❌ 只有伺服器管理員（版主）才能執行此指令！", ephemeral=True
      )
      return False
    return True

  return app_commands.check(predicate)


# 檢查是否在專屬版面的 Decorator
def in_exclusive_channel():
  async def predicate(interaction: discord.Interaction):
    channel = interaction.channel
    is_valid = False
    if interaction.channel_id == EXCLUSIVE_CHANNEL_ID:
      is_valid = True
    elif (
        isinstance(channel, discord.Thread)
        and channel.parent_id == EXCLUSIVE_CHANNEL_ID
    ):
      is_valid = True

    if not is_valid:
      await interaction.response.send_message(
          f"❌ 此指令只能在專屬版面 <#{EXCLUSIVE_CHANNEL_ID}> 中使用！",
          ephemeral=True,
      )
      return False
    return True

  return app_commands.check(predicate)


@bot.tree.command(name="add_schedule", description="[版主專用] 在課表中填入內容")
@app_commands.describe(
    date="日期 (格式：YYYY-MM-DD)", period="選擇節次", content="要填入的內容"
)
@app_commands.choices(
    period=[
        app_commands.Choice(
            name="第0節早自修 (07:30-08:00)", value="第0節早自修"
        ),
        app_commands.Choice(name="第1節 (08:10-08:55)", value="第1節"),
        app_commands.Choice(name="第2節 (09:15-10:00)", value="第2節"),
        app_commands.Choice(name="第3節 (10:10-10:55)", value="第3節"),
        app_commands.Choice(name="第4節 (11:05-11:50)", value="第4節"),
        app_commands.Choice(name="第5節 (13:10-13:55)", value="第5節"),
        app_commands.Choice(name="第6節 (14:10-14:55)", value="第6節"),
        app_commands.Choice(name="第7節 (15:10-15:55)", value="第7節"),
        app_commands.Choice(name="第8節 (16:05-16:50)", value="第8節"),
        app_commands.Choice(name="第9節 (16:55-17:40)", value="第9節"),
        app_commands.Choice(name="第10節 (17:45-18:30)", value="第10節"),
    ]
)
@is_admin()
@in_exclusive_channel()
async def slash_add_schedule(
    interaction: discord.Interaction,
    date: str,
    period: str,
    content: str,
):
  try:
    input_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
  except ValueError:
    await interaction.response.send_message(
        "❌ 日期格式錯誤，請使用 `YYYY-MM-DD`（例如 `2026-09-14`）。",
        ephemeral=True,
    )
    return

  # 檢查是否為已存在考試日期的前一天
  # 假設已有的考試日期存在 exams_data 中，這裡我們對比所有的考試日期
  is_valid_day = False
  # 收集目前所有的考試日期 (假設內容或備註有安排考試，或是比對所有已登記的日期)
  # 這裡以比對現有所有排程日期（或特定考試標記）的前一天為例：
  existing_dates = set(e.get("date") for e in exams_data)

  for d_str in existing_dates:
    try:
      d_obj = datetime.datetime.strptime(d_str, "%Y-%m-%d").date()
      if input_date == d_obj - datetime.timedelta(days=1):
        is_valid_day = True
        break
    except ValueError:
      continue

  # 如果完全沒有任何排程，或者剛好是某個排程日期的前一天，則允許新增
  # 如果你想嚴格規定「必須是某個已有考試日期的前一天」，當 existing_dates 為空時也可以彈性放行或要求
  if existing_dates and not is_valid_day:
    # 組合提示哪些日期的前一天是可以被接受的
    valid_suggestions = [
        (
            datetime.datetime.strptime(d, "%Y-%m-%d").date()
            - datetime.timedelta(days=1)
        ).strftime("%Y-%m-%d")
        for d in existing_dates
    ]
    await interaction.response.send_message(
        f"❌ 檢查失敗！新增的日期 `{date}` 必須是現有考試日期的**前一天**。\n💡 允許的前一天日期為：`{', '.join(set(valid_suggestions))}`",
        ephemeral=True,
    )
    return

  new_id = max([e["id"] for e in exams_data], default=0) + 1
  new_exam = {"id": new_id, "date": date, "period": period, "content": content}
  exams_data.append(new_exam)

  target_channel = (
      interaction.channel
      if isinstance(interaction.channel, discord.Thread)
      else bot.get_channel(EXCLUSIVE_CHANNEL_ID)
  )
  if target_channel:
    await update_or_create_dashboard(target_channel)

  await interaction.response.send_message(
      f"✅ [前一天檢查通過] 成功填入課表 (ID: {new_id})：`{date}` | `{period}`",
      ephemeral=True,
  )


@bot.tree.command(name="del_schedule", description="[版主專用] 透過項目 ID 刪除內容")
@app_commands.describe(schedule_id="要刪除的項目 ID")
@is_admin()
@in_exclusive_channel()
async def slash_del_schedule(
    interaction: discord.Interaction, schedule_id: int
):
  global exams_data
  initial_len = len(exams_data)
  exams_data = [e for e in exams_data if e["id"] != schedule_id]

  if len(exams_data) < initial_len:
    target_channel = (
        interaction.channel
        if isinstance(interaction.channel, discord.Thread)
        else bot.get_channel(EXCLUSIVE_CHANNEL_ID)
    )
    if target_channel:
      await update_or_create_dashboard(target_channel)
    await interaction.response.send_message(
        f"🗑️ 已成功刪除 ID 為 #{schedule_id} 的項目！", ephemeral=True
    )
  else:
    await interaction.response.send_message(
        f"❌ 找不到 ID 為 #{schedule_id} 的項目。", ephemeral=True
    )


@bot.tree.command(name="init_dashboard", description="[版主專用] 生成課表面板")
@is_admin()
@in_exclusive_channel()
async def slash_init_dashboard(interaction: discord.Interaction):
  target_channel = interaction.channel
  await update_or_create_dashboard(target_channel)
  await interaction.response.send_message(
      "✅ 互動式 HTML 課表面板已成功生成！", ephemeral=True
  )


@bot.tree.command(name="檢視課表", description="[專屬版面] 開啟內嵌互動式課表介面")
@in_exclusive_channel()
async def slash_view_schedule(interaction: discord.Interaction):
  web_url = os.environ.get(
      "RENDER_External_URL", "https://mybot-v6cj.onrender.com"
  )
  view = discord.ui.View(timeout=None)
  view.add_item(
      discord.ui.Button(
          label="📅 點擊開啟內嵌課表",
          style=discord.ButtonStyle.link,
          url=web_url,
      )
  )
  await interaction.response.send_message(
      "請點擊下方按鈕開啟互動課表：", view=view, ephemeral=True
  )


if __name__ == "__main__":
  threading.Thread(target=run_flask, daemon=True).start()
  token = os.environ.get("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE")
  bot.run(token)
