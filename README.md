# Discord Staff Bot

بوت لإدارة فريق الإدارة في السيرفر مع أنظمة: التوظيف، الترقية، التقييم، الإجازات، الحضور، الإحصائيات، والـ Logs.

## التشغيل

1. ثبّت المتطلبات:

```bash
pip install -r requirements.txt
```

2. أنشئ ملف `.env`:

```env
DISCORD_TOKEN=YOUR_TOKEN
GUILD_ID=123456789012345678
LOG_CHANNEL_NAME=bot-logs
STAFF_MANAGER_ROLE=Staff Manager
```

3. شغّل البوت:

```bash
python bot.py
```

## الأوامر

- `!توظيف @user`
- `!ترقية @user [steps]`
- `!تنزيل @user [steps]`
- `!ترقية-فئة @user [steps]`
- `!فصل @user`
- `!اجازة @user <hours>`
- `!تسجيل`
- `!خروج`
- `!say <message>`
- `/stats`
- `/rate @staff`
- `/love person1 person2` (يدعم منشن / ID / username)

## ترتيب الرتب والفئات

- STAFF:
  - Trial Staff
  - Trainee
  - Helper
  - Visor
  - Senior
  - Moderator
  - Senior Moderator
  - Head Moderator
- MIDDLE STAFF:
  - designer
  - Agon
  - Advisor
  - Developer
- HIGHER MANAGEMENT:
  - Co Manager
  - Manager
  - Co Leader
  - Leader
- OWNER:
  - RIGHT HAND
  - LEFT HAND

## ملاحظات مهمة

- رتب الفئات (`STAFF`, `MIDDLE STAFF`, `HIGHER MANAGEMENT`, `OWNER`) لا تُحذف في الترقية/التنزيل العادي، وتُضاف تلقائياً عند الانتقال لفئة أعلى.
- كل البيانات محفوظة في ملفات JSON داخل `data/`.
- يجب أن تكون الرتب في السيرفر مطابقة للأسماء المعرّفة في `bot.py`.


## لوحة تحكم (Dashboard)

تمت إضافة لوحة تحكم ويب للعمل من Termux وتشمل إدارة البوت:

- عرض الإحصائيات (ratings / vacations / attendance / stats).
- إرسال أوامر إدارية مباشرة للبوت (توظيف / ترقية / تنزيل / ترقية-فئة / فصل / إجازة) عبر Queue.
- البوت ينفذ أوامر الـ Dashboard تلقائياً كل عدة ثواني.

### تشغيل اللوحة

1. أضف في `.env`:

```env
DASHBOARD_TOKEN=YOUR_SECRET_TOKEN
DASHBOARD_PORT=8080
```

2. شغّل اللوحة:

```bash
python dashboard.py
```

3. افتح من المتصفح:

```
http://127.0.0.1:8080/?token=YOUR_SECRET_TOKEN
```

> ملاحظة: يجب أن يكون `bot.py` شغال بنفس الوقت حتى ينفذ الأوامر المرسلة من اللوحة.
