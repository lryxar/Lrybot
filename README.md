# Discord Staff Bot

بوت متكامل لإدارة فريق الإدارة + أنظمة تفاعل للأعضاء (عملة ALR Coins + نظام لفل).

## التشغيل

1. تثبيت المتطلبات:

```bash
pip install -r requirements.txt
```

2. إنشاء ملف `.env`:

```env
DISCORD_TOKEN=YOUR_TOKEN
GUILD_ID=123456789012345678
LOG_CHANNEL_NAME=bot-logs
STAFF_MANAGER_ROLE=Staff Manager
```

3. تشغيل البوت:

```bash
python bot.py
```

## أوامر الإدارة

- `!توظيف @user`
- `!ترقية @user [steps]`
- `!تنزيل @user [steps]`
- `!ترقية-فئة @user [steps]`
- `!فصل @user`
- `!اجازة @user <hours>`
- `!تسجيل`
- `!خروج`
- `!say <message>`

## أوامر سلاش

- `/rate`
- `/stats`
- `/profile`
- `/top_alr`
- `/love person1 person2`

## نظام ALR Coins + Level

- كل عضو يحصل على ALR Coins من التفاعل (الرسائل المؤهلة).
- كل رسالة مؤهلة تعطي XP.
- المستوى الأول يحتاج 100 رسالة.
- كل مستوى جديد أصعب بنسبة 15%.
- رتب المستوى:
  - Level 10
  - Level 20
  - Level 30
  - Level 40
  - Level 50
  - Level 60
  - Level 70
  - عند لفل 80: `Great Member` (بدل Level 80)

## ملاحظات مهمة

- رتب الفئات (`STAFF`, `MIDDLE STAFF`, `HIGHER MANAGEMENT`, `OWNER`) لا تُحذف في الترقية/التنزيل العادي، ويتم إضافتها تلقائياً حسب الرتبة.
- بيانات التخزين موجودة في `data/`:
  - `ratings.json`
  - `vacations.json`
  - `attendance.json`
  - `stats.json`
  - `economy.json`
