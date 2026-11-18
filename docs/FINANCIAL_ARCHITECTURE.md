# مشخصات نهایی و یکپارچه معماری مالی — DriverManagement

**وضعیت سند:** SPECIFICATION — **پیاده‌سازی کامل در 2026-11-10 توسط کاربر اجازه داده شد (AUTHORIZED).** قوانین تجاری این سند قطعی و لازم‌الاجرا هستند.
**تاریخ تحکیم:** 2026-11-10
**مرجعیت:** این سند، سند واحد و حاکم طراحی مالی است و جایگزین همه اسناد طراحی قبلی (گزارش‌های OpenCode، حسابرسی مستقل، مشخصات اصلاح‌شده، اصلاح وابستگی‌ها، بازبینی سه‌مسئله‌ای و اصلاح T5) می‌شود. هر سند قبلی که Own-First را `PROPOSED` یا «نیازمند تأیید» توصیف کرده بود، از تاریخ 2026-11-10 منسوخ است: **Own-First اکنون `CONFIRMED — FINAL BUSINESS RULE` است** (تأیید صریح کاربر).

---

## ۰. واقعیت‌های پایه (تأییدشده با بازرسی پروژه)

| واقعیت | شاهد |
|---|---|
| اپ مالی هنوز ساخته نشده؛ `apps.payments` scaffold خالی است | `backend/apps/payments/models.py:1-5` |
| هیچ جدول مالی در دیتابیس واقعی وجود ندارد؛ migrations مالی اعمال نشده | بازرسی read-only دیتابیس در فاز حسابرسی |
| SQLite است؛ `select_for_update()` روی آن **بی‌اثر (no-op)** است | `backend/.venv314/lib/python3.14/site-packages/django/db/backends/base/features.py:49` (`has_select_for_update = False`) و `compiler.py:839` |
| احراز هویت: User داخلی جنگو، SessionAuthentication، `IsAuthenticated` پیش‌فرض، تک‌ادمین آفلاین | `backend/config/settings.py:169-184`، `backend/apps/core/views.py` |
| منطقه زمانی `Asia/Kabul`، `USE_TZ=True`، timeout=20 | `backend/config/settings.py:107-116,141` |
| قوانین تجاری پایه | `README.md:200,211-213` |
| سابقه soft-delete و الگوی خطای فارسی | `backend/apps/documents/models.py:122-125`، `backend/apps/drivers/views.py:97-105` |
| آسیب‌پذیری فعلی: `fee_start_date` از API قابل نوشتن است (باید read-only شود) | `backend/apps/drivers/serializers.py:91,98` |

---

## ۱. قوانین تجاری تأییدشده — CONFIRMED, FINAL BUSINESS RULES

این تصمیمات **قطعی** هستند و هرگز بازپرسیده نمی‌شوند:

| # | قانون |
|---|---|
| C1 | فیس استاندارد: **600 AFN هر سه ماه تقویمی** (تغییر مبلغ فقط از مسیر FeeSchedule §۸) |
| C2 | **پرداخت جزئی مجاز است** |
| C3 | فقط دوره‌های **سررسیدگذشته** در بدهی معوق شمرده می‌شوند. `due_date(period) = period.end_date`؛ **معوق ⇔ `due_date < today`** (تاریخ محلی Asia/Kabul). دوره جاری هرگز معوق نیست؛ بدون دوره ارفاق |
| C4 | **مدیر دوره‌های هدف را انتخاب می‌کند**؛ FIFO فقط یک پیشنهاد نمایشی است |
| C5 | **مصرف اعتبار فقط با تأیید صریح مدیر** ثبت می‌شود |
| C6 | اضافه‌پرداخت به **اعتبار قابل ردیابی** تبدیل می‌شود (نه درآمد، نه بدهی منفی) |
| C7 | **درآمد نقدی و تسویه دوره دو مفهوم جدا** هستند؛ مصرف اعتبار درآمد نقدی را زیاد نمی‌کند |
| C8 | **هیچ رکورد تاریخی بی‌صدا حذف نمی‌شود** — append-only؛ حذف سخت ممنوع |
| C9 | **اصلاح پرداخت و اصلاح allocation دو عملیات جدا** هستند |
| C10 | **Own-First — CONFIRMED, FINAL BUSINESS RULE (تأیید صریح کاربر، 2026-11-10):** اولویت کاهش تعهدات هر دوره: (۱) فیس خود راننده در همان دوره، (۲) قدیمی‌ترین تعهد انتقالی ورودی، (۳) تعهدات انتقالی جدیدتر. ترتیب انتقال‌ها قطعی با `(effective_date, id)` صعودی. پیامدهای تأییدشده همین بسته: عدم earmark پرداخت به انتقال خاص درون دوره؛ ظرفیت reversal وابسته به ترتیب؛ قاعده مشروط downstream-first (§۵) |

---

## ۲. رجیستر تصمیم‌ها

### ۲.۱ CONFIRMED — تصمیمات تجاری کاربر
همه ردیف‌های C1–C10 §۱. وضعیت: **FINAL**. تاریخ تأیید C10: 2026-11-10 (وضعیت پیشین آن PROPOSED بود؛ اکنون منسوخ).

### ۲.۲ DERIVED — نتایج اثبات‌شده حسابداری/طراحی (پذیرفته‌شده در مرورهای طراحی)
این‌ها پیامدهای ریاضی/حسابداری قوانین تأییدشده یا اصلاحات ضروری حسابرسی هستند — تصمیم تجاری جدید نیستند:

| # | نتیجه | مبنا |
|---|---|---|
| D1 | Doctrine بدون-backdate: ثبت دیرهنگام **نقد واقعی گذشته** مجاز (`payment_date` گذشته)؛ correction/void/reversal/تغییر فیس/تغییر era هرگز backdate نمی‌شوند | سازگاری as-of؛ جلوگیری از دوباره‌شماری |
| D2 | هر رکورد مالی سه زمان دارد: `effective_date` (تجاری)، `created_at` (حسابرسی)، timestamp رخداد (`voided_at/corrected_at/reversed_at`) | رفع H1–H3 |
| D3 | دوره‌ها **computed** از لنگر era؛ جدول Period وجود ندارد | رفع H6؛ عدم هم‌پوشانی by-construction |
| D4 | قاعده era: `effective = ceil_to_grid(max(requested, current_period_end + 1))` | حفظ دوره‌های آغازشده |
| D5 | FeeSchedule append-only؛ `fee(period) = amount آخرین ردیف با effective_from ≤ period.start` | حفظ فیس تاریخی (P2) |
| D6 | DriverFeeHistory append-only؛ `fee_start_date` در API/admin **read-only** + endpoint اختصاصی با reason | رفع آسیب‌پذیری serializers.py:91 |
| D7 | `status` تنها منبع حقیقت اعتبار پرداخت؛ `is_void`/`is_reversed` فقط property مشتق — ستون نیستند | drift غیرممکن |
| D8 | reversalها **ردیف append-only جدید**؛ اصل mutate نمی‌شود؛ فیلد `reversal_at` روی اصل وجود ندارد؛ reversalها terminalاند | رفع E5 |
| D9 | پشته تعهدات Own-First (§۵)؛ cap انتقال: `R ≤ remaining_Ti`؛ این خودکار `Σ reversals ≤ original.amount` را نیز پوشش می‌دهد | اصلاح T5؛ قاعده aggregate ناکافی/غلط بود |
| D10 | capهای نوشتنی: transfer/waiver `≤ source_balance`؛ consumption `≤ MIN(source_available, target_need)` **پیش از INSERT** | رفع E2/E3 |
| D11 | دریافت جدید از دوره هدف آغاز و به‌ترتیب میان مانده‌های دوره‌های متوالی (با احتساب بدهی انتقال‌یافته) تا تخصیص کامل تقسیم می‌شود؛ `CREDIT` جدید ساخته نمی‌شود. اعتبارهای تاریخی و اعتبار حاصل از W9/W5-ext حفظ می‌شوند | تخصیص خودکار بدون حذف سابقه |
| D12 | اصلاح allocation با مصرف وابسته = W5-ext (§۷): reverse مصرف‌ها → reverse منبع → جایگزین‌ها → **تأیید مجدد مدیر**؛ سوئیچ هم‌روز as-of | بدون تکرار/گمشدگی |
| D13 | گردش کار W9 (un-settle سپس reversal) وقتی ظرفیت reversal مقصد صفر است | رفع E4/P1 |
| D14 | معادلات پایستگی (O)/(C)/(S) (§۶)؛ ادعای «ثبات بدهی هنگام تسویه نقدی» **باطل و منسوخ** است | اصلاح N4 |
| D15 | `gross_allocation_total` (تاریخی، می‌تواند > amount) در برابر `active_allocation_total` ( تنها دارای invariant ≤ amount)؛ `unallocated` سطل suspense دیدبان | بازبینی §۱ سند چهارم |
| D16 | زنجیره انتقال: downstream-first **مشروط** — فقط وقتی `remaining_upstream < R`؛ وابستگی در پشته کدگذاری می‌شود نه لینک ذخیره‌شده | proof زنجیره §۱۱ |
| D17 | `Payment.effective_date` (رؤیت‌پذیری) جدا از `payment_date` (انتساب نقد)؛ پرداخت جایگزین correction: `effective_date = روز correction`، `payment_date = تاریخ واقعی نقد` | رفع دوباره‌شماری 1200 در R2 |

### ۲.۳ TECHNICAL IMPLEMENTATION DECISIONS — تصمیمات فنی (ratify‌شده در جریان پیاده‌سازی 2026-11-10)

| # | تصمیم | دلیل |
|---|---|---|
| T1 | الگوی validate → insert داخل `transaction.atomic()`؛ برای سقف تجمیعی Refund، ردیف Payment با `select_for_update()` قفل می‌شود تا درخواست‌های هم‌زمان نتوانند از سقف عبور کنند | SQLite این قفل را نادیده می‌گیرد؛ PostgreSQL آن را اعمال می‌کند |
| T2 | دفاع عمقی: triggerهای `BEFORE INSERT/UPDATE` با `RunSQL` برای invariantهای aggregate + `CheckConstraint` برای row-level | invariant حیاتی حتی با SQL خام نقض‌ناپذیر |
| T3 | قرارداد **تمام‌AFN** (validator) | SUMهای SQLite دقیقاً integer؛ بدون خطای شناور |
| T4 | `idempotency_key` / `consumption_id` یکتا | retry امن |
| T5 | `receipt_number` اختیاری و غیر-unique | سادگی دفتر تک‌ادمین |
| T6 | ترتیب touch ثابت (همیشه ریشه Payment/Driver) | بدون deadlock |
| T7 | `timeout=20` موجود؛ نگاشت خطای قفل به 409/400 فارسی | contention تقریباً صفر |
| T8 | caching/ایندکس‌گذاری بازسازی دوره‌ها در صورت نیاز | تصمیم اجرایی، نه حسابداری |
| T9 | فازبندی migration با دروازه اجازه مرحله‌ای؛ backup اول؛ verify روی **کپی** دیتابیس | ایمنی داده موجود |
| T10 | اجرای V1–V10 فقط روی دیتابیس **موقت ایزوله** (مطابق اجازه پیاده‌سازی 2026-11-10) | محدودیت صریح کاربر |

---

## ۳. معماری موجودیت‌ها و روابط

```
Driver (موجود، بدون تغییر ساختاری)
  │ 1───N  DriverFeeHistory        (drivers app — eraهای fee_start_date، append-only)
  │ 1───N  Payment                 (payments app)
               │ 1───N  PaymentAllocation  (fee_period | credit؛ اعتبارهای تاریخی و بازتخصیص‌های اصلاحی)
               │ 1───N  PaymentRefund      (برگشت نقد مستقل و append-only)
               │             │ 1───N  AllocationConsumption  (فقط از منبع credit)
               │ self-FK: correction_of → پرداخت اصلی (روی پرداخت جدید)
               │ PaymentAllocation.self-FK: correction_of → allocation اصلی
               │ PaymentRefund ← refunded_by / refund_date / reason
  Adjustment (payments app — waiver | transfer | waiver_reversal | transfer_reversal)
               │ self-FK: reverses_adjustment → adjustment اصلی
  FeeSchedule  (payments app — مبلغ فیس جهانی، append-only)

User (django.contrib.auth.User) ← created_by/allocated_by/consumed_by/reversed_by/
                                    voided_by/corrected_by/refunded_by/changed_by (همه PROTECT)
```

**اصل معماری:** پول نقد فقط در `Payment` خلق می‌شود. `PaymentRefund` آن را با یک رکورد منفی مستقل کاهش می‌دهد؛ `Payment` تغییر نمی‌کند. `PaymentAllocation` ادعای جهت‌دار روی همان نقد است (جمع active ≤ مبلغ خالص پس از Refund). `AllocationConsumption` ادعا را از استخر credit به دوره منتقل می‌کند — پولی خلق نمی‌کند. `Adjustment` فقط بدهی را جابه‌جا/می‌بخشد — هرگز نقد نمی‌سازد. دوره‌ها محاسبه می‌شوند، ذخیره نمی‌شوند.

---

## ۴. فیلدها و قیود دقیق هر مدل

### ۴.۱ Payment (`apps.payments`)

| فیلد | نوع / قید |
|---|---|
| driver | FK(`drivers.Driver`, PROTECT, related_name=`payments`) |
| amount | DecimalField(10,2)، `CheckConstraint(amount > 0)`؛ validator تمام‌AFN (T3) |
| payment_date | DateField — **تاریخ واقعی دریافت نقد / انتساب به بازه گزارش**؛ backdate برای ثبت دیرهنگام نقد واقعی مجاز؛ validator `payment_date ≤ today` |
| effective_date | DateField — **تاریخ رؤیت‌پذیری در گزارش‌ها**؛ رسید عادی = `payment_date`؛ **پرداخت جایگزین correction = روز تصمیم correction** (هرگز backdate)؛ برای غیرcorrectionها `effective_date = payment_date` (D17) |
| receipt_number | CharField(50), blank=True, default='' (اختیاری، غیر-unique — T5) |
| idempotency_key | CharField(64), unique=True, null=True, blank=True |
| status | CharField(20), choices=`received/voided/corrected`, default=`received` — **تنها منبع حقیقت اعتبار** |
| correction_of | FK(`self`, PROTECT, null=True, blank=True, related_name=`corrections`) — روی پرداخت **جدید** |
| void_reason / correction_reason | TextField, blank=True |
| voided_at / corrected_at | DateTimeField, null=True, blank=True |
| voided_by / corrected_by | FK(User, PROTECT, null=True, blank=True) |
| created_by | FK(User, PROTECT)؛ created_at auto_now_add؛ updated_at auto_now |

**قیود (CheckConstraint):** `status='voided' ⇒ voided_at NOT NULL AND void_reason ≠ '' AND voided_by NOT NULL`؛ `status='corrected' ⇒ corrected_at NOT NULL AND correction_reason ≠ '' AND corrected_by NOT NULL`؛ `status='received' ⇒ voided_at IS NULL AND corrected_at IS NULL`. **`is_void` ستون نیست** — property: `is_void = (status != 'received')`. حذف سخت ممنوع: `delete()` raise + admin `has_delete_permission=False`. Indexها: `(driver, payment_date)`، `status`.

### ۴.۲ PaymentAllocation

| فیلد | نوع / قید |
|---|---|
| payment | FK(Payment, PROTECT, related_name=`allocations`) |
| allocation_type | choices=`fee_period/credit` |
| target_period_start / target_period_end | DateField, null — **NOT NULL iff fee_period؛ NULL iff credit** (CheckConstraint)؛ `start ≤ end` |
| allocated_amount | DecimalField(10,2), `> 0` |
| effective_date | DateField — پیش‌فرض `payment.payment_date`؛ **در correction هرگز backdate نمی‌شود** (= روز اصلاح) |
| correction_of | FK(`self`, PROTECT, null=True, related_name=`allocation_corrections`) |
| reversed_at / reversed_by / reversal_reason | DateTimeField null / FK(User) null / TextField blank — **ستون `is_reversed` وجود ندارد**؛ وضعیت = `reversed_at IS NULL` |
| allocated_by | FK(User, PROTECT)؛ created_at auto_now_add |

**قیود:** reversed ⇒ reason ≠ '' AND by NOT NULL. **Invariant aggregate (غیرقابل بیان در CHECK.row):** `SUM(allocated_amount WHERE payment_id=p AND reversed_at IS NULL) ≤ p.amount` — سرویس اتمیک + trigger (§۹). Indexها: `payment`، `(target_period_start, target_period_end)`.

### ۴.۳ AllocationConsumption

| فیلد | نوع / قید |
|---|---|
| source_allocation | FK(PaymentAllocation, PROTECT, related_name=`consumptions`) — باید `allocation_type='credit'` (سرویس + trigger) |
| consumption_amount | DecimalField(10,2), `> 0` |
| target_period_start / target_period_end | DateField, NOT NULL, `start ≤ end` |
| effective_date | DateField = تاریخ تأیید مدیر (بدون backdate) |
| consumption_id | CharField(64), unique=True (idempotency) |
| consumed_by | FK(User, PROTECT) — **تأیید صریح مدیر** (C5) |
| reason | TextField, blank=True |
| reversed_at / reversed_by / reversal_reason | همان الگوی §۴.۲ |
| consumed_at | auto_now_add |

**قید نوشتنی:** `consumption_amount ≤ MIN(source_available_balance, target_period_balance)` — پیش از INSERT، اتمیک (W2). Indexها: `source_allocation`، `(target_period_start, target_period_end)`.

### ۴.۴ Adjustment

| فیلد | نوع / قید |
|---|---|
| adjustment_type | choices=`waiver/transfer/waiver_reversal/transfer_reversal` |
| amount | DecimalField(10,2), `> 0` |
| source_period_start / source_period_end | DateField, NOT NULL |
| destination_period_start / destination_period_end | DateField, null — NOT NULL iff transfer/transfer_reversal |
| reverses_adjustment | FK(`self`, PROTECT, null=True, related_name=`reversals`) — NOT NULL iff reversal؛ نوع جفت (`transfer_reversal → transfer`) |
| reason | TextField, **غیرخالی** |
| effective_date | DateField = تاریخ تصمیم (بدون backdate) |
| created_by / created_at | FK(User, PROTECT) / auto_now_add |

**الگو:** reversalها ردیف append-only جدید؛ اصل هرگز mutate نمی‌شود؛ `reversal_at` روی اصل وجود ندارد (D8)؛ reversalها terminalاند. **قیود نوشتنی:** `Σ reversals.amount ≤ original.amount`؛ transfer: `amount ≤ source_balance`؛ waiver: `amount ≤ source_balance`؛ **transfer_reversal: `amount ≤ remaining_Ti` (پشته Own-First، §۵)** — این جایگزین قاعده قدیمی aggregate `≤ destination_balance` شده است. انواع `settlement/correction` عمداً وجود ندارند (settlement همان allocation است).

### ۴.۵ FeeSchedule

| فیلد | نوع / قید |
|---|---|
| amount | DecimalField(10,2), `> 0` (ردیف اولیه: 600) |
| effective_from | DateField, **unique**؛ validator `effective_from ≥ created_at::date` (بدون backdate) |
| reason | TextField غیرخالی؛ created_by FK(User, PROTECT)؛ created_at auto_now_add |

Append-only؛ UPDATE/DELETE ممنوع. ردیف اولیه در data migration با `effective_from = 1900-01-01`.

### ۴.۶ PaymentRefund

| فیلد | نوع / قید |
|---|---|
| payment | FK(Payment, PROTECT, related_name=`refunds`) |
| amount | DecimalField(10,2)، `> 0`؛ تمام-AFN |
| refund_date | DateField — تاریخ واقعی برگشت نقد، بدون تاریخ آینده |
| effective_date | DateField — روز ثبت Refund در Ledger، بدون backdate |
| reason | TextField غیرخالی |
| refunded_by | FK(User, PROTECT) |
| created_at | auto_now_add |

رکورد Refund مستقل و append-only است. سقف تجمیعی: `SUM(refunds.amount) ≤ payment.amount`. Refund در transaction، ابتدا مقدار unallocated را کاهش می‌دهد و سپس allocationهای لازم را با reversal و ردیف‌های جایگزین بازسازی می‌کند؛ برای credit، مصرف‌های وابسته فقط تا موجودی و نیاز معتبر دوباره ثبت می‌شوند. Refund با void/correction روی همان پرداخت ترکیب نمی‌شود.

### ۴.۶ DriverFeeHistory (`apps.drivers`)

| فیلد | نوع / قید |
|---|---|
| driver | FK(Driver, PROTECT, related_name=`fee_history`) |
| old_fee_start_date | DateField, null (ردیف اولیه: NULL) |
| requested_fee_start_date | DateField — درخواست مدیر |
| effective_fee_start_date | DateField — **لنگر era** طبق §۸.۳ |
| reason | TextField غیرخالی؛ changed_by FK(User, PROTECT)؛ changed_at auto_now_add |

Append-only. ردیف اولیه هنگام ایجاد Driver (همان transaction). `Driver.fee_start_date` فقط آینه نمایشی آخرین requested است؛ بازسازی از history می‌خواند.

---

## ۵. قاعده Own-First و پشته تعهدات — CONFIRMED, FINAL BUSINESS RULE

**اولویت کاهش (قطعی، تأییدشده 2026-11-10):** فیس خود دوره → قدیمی‌ترین انتقال ورودی → انتقال‌های جدیدتر. ترتیب انتقال‌ها: `(effective_date, id)` صعودی — total order قطعی (tie با id).

```
obligations(period) = [fee] + [T_i.net به ترتیب (effective_date, id)]
   که T_i.net = amount_i − Σ reversalهای همان انتقال (ردیف‌های append-only)
reductions(period)  = net_waiver + cash_settled + credit_settled + net_transfer_out

remaining_own = fee − MIN(reductions, fee)
remaining_Ti  = Ti.net − CLAMP(reductions − fee − Σ_{j<i} Tj.net, 0, Ti.net)
period_balance = remaining_own + Σ remaining_Ti
```

**خواص اثبات‌شده:**
- تابع خالص رکوردهای immutable ⇒ قطعی و در هر as-of D بازتولیدپذیر.
- `period_balance = MAX(0, fee + ΣTi.net − reductions)` وقتی capها رعایت شوند (بدون clipping) — جمع کل با ترتیب عوض نمی‌شود؛ فقط **توزیع** remaining و **ظرفیت reversal هر انتقال** به ترتیب وابسته است.
- **cap reversal انتقال:** `R ≤ remaining_Ti`. چون `remaining_Ti ≤ Ti.net = amount_i − Σ_prev`، این خودکار `Σ reversals ≤ amount_i` را پوشش می‌دهد (گارد پشته سخت‌گیرانه‌تر و مقیدکننده است).
- **انتقال خروجی** نیز از پشته مبدأ با همین اولویت مصرف می‌کند ⇒ `remaining` انتقال بالادستی در دوره میانی کاهش می‌یابد.
- **قاعده زنجیره (D16):** downstream فقط وقتی باید اول reverse شود که transferهای downstream یا settlementها تعهد بالادستی را مصرف کرده باشند (`remaining_upstream < R`). پشته این را خودکار محاسبه می‌کند؛ هیچ graph وابستگی ذخیره‌شده لازم نیست.
- **محدودیت پذیرفته‌شده (بخشی از بسته تأییدشده C10):** مدیر نمی‌تواند پرداختی را درون دوره به انتقال خاصی earmark کند. اگر روزی لازم شد، `ledger.application` توسعه آینده است (خارج از دامنه فعلی).
- مانده منفی دوره مجاز نیست؛ capهای نوشتنی (§۷) تضمین می‌کنند `reductions ≤ fee + ΣTi.net`.

---

## ۶. فرمول‌های حسابداری و معادلات پایستگی

### ۶.۱ Predicateها (نسخه نهایی — جایگزین همه نسخه‌های قبلی)

```
valid_payment(p)    ⇔ p.status = 'received'
active(r)           ⇔ r.reversed_at IS NULL
active_as_of(r, D)  ⇔ r.effective_date ≤ D AND (r.reversed_at IS NULL OR r.reversed_at > D)
valid_as_of(p, D)   ⇔ p.effective_date ≤ D
                      AND (p.voided_at   IS NULL OR p.voided_at   > D)
                      AND (p.corrected_at IS NULL OR p.corrected_at > D)
recorded_as_of(p,D) ⇔ p.created_at ≤ D AND timestampهای ابطال/اصلاح رعایت‌شده   -- فقط حسابرسی

-- سازگاری: با doctrine بدون-backdate، valid_as_of(p, today) ≡ status='received'
```

### ۶.۲ Aggregateها

```
fee(period)            = FeeSchedule.amount با بیشترین effective_from ≤ period.start
cash_settled(period)   = SUM(active fee_period allocations → period, payment معتبر)
credit_settled(period) = SUM(active consumptions → period, منبع و پرداخت معتبر)
net_waiver(period)     = Σ waiver.amount − Σ waiver_reversal.amount
net_xfer_out/in(period)= Σ transfer.amount − Σ transfer_reversal.amount (به تفکیک مبدأ/مقصد)
period_balance(period) = remaining_own + Σ remaining_Ti          -- پشته §۵ (تعریف حاکم)

gross_allocation_total(p)  = SUM(allocated_amount همه ردیف‌ها)   -- فقط تاریخ/حسابرسی
active_allocation_total(p) = SUM(allocated_amount WHERE reversed_at IS NULL)  -- ≤ p.amount
unallocated(p)             = p.amount − active_allocation_total(p)            -- سطل دیدبان
source_available(sa)       = sa.allocated_amount − Σ active consumptions از sa
available_credit(driver)   = Σ active credit allocations − Σ active consumptions

current_obligation(driver) = period_balance(دوره‌ای که start ≤ today ≤ end)
overdue_debt(driver)       = Σ period_balance(p) WHERE p.end_date < today   -- فقط سررسیدگذشته (C3)
driver_total_balance       = Σ period_balance(همه دوره‌های بازسازی‌شده)      -- جدا از overdue
```

### ۶.۳ معادلات پایستگی — فهرست کامل با معنی

| # | معادله | معنی |
|---|---|---|
| (P) | `amount = fee_allocated + credit_allocated + unallocated` (active، per payment) | هر AFN نقد دقیقاً در یک سطل؛ افراز disjoint |
| (CR) | `credit_allocated = consumed + available` (per source) | اعتبار یا مصرف شده یا موجود است؛ هرگز هر دو |
| (O) | `OutstandingDebt + Waived + SettledByCash + SettledByCredit = TotalFeeObligations` | پایستگی تعهدات: بدهی فقط با تسویه نقدی/اعتباری/waiver کم می‌شود — **نه ثابت می‌ماند، نه بی‌حساب کم می‌شود** |
| (C) | `CashReceived = SettledByCash + ConsumedCredit + AvailableCredit + UnallocatedCash` | پایستگی نقد: هر AFN دریافتی دقیقاً یک‌بار حساب می‌شود |
| (S) | `SettledByCredit = ConsumedCredit` | تسویه اعتباری دقیقاً همان مصرف تأییدشده است |
| (T) | `Σ net_xfer_out = Σ net_xfer_in` (سطح راننده) ⇒ `Δdebt = 0` برای transfer و transfer_reversal | انتقال/بازگشت آن فقط بدهی را بین دوره‌ها جابه‌جا می‌کند؛ خلق/نابود نمی‌کند |
| (R) | `R ≤ remaining_Ti ≤ Ti.net ⇒ Σ reversals ≤ original.amount` | reversal علیه مانده unpaid **همان انتقال**؛ سقف cumulative خودکار |

**اثر هر عملیات بر هویت‌ها:** دریافت نقد R: (C) دو طرف +R، (O) دست‌نخورده. allocation به fee: Unallocated −A، SettledByCash +A، Debt −A ⇒ (O) دو طرف −A. allocation به credit: Unallocated −A، Available +A. مصرف: Available −A، Consumed +A، SettledByCredit +A، Debt −A. waiver: Waived +A، Debt −A. transfer/reversal: فقط توزیع دوره‌ای. void پرداخت + زنجیره فرزندان: همه سطل‌ها برعکس، اتمیک با timestamp یکسان.

### ۶.۴ Invariantهای اجباری (خلاصه enforceable)

1. `active_allocation_total(p) ≤ p.amount` — سرویس اتمیک + trigger.
2. `consumption ≤ MIN(source_available, target_need)` — پیش از INSERT.
3. `transfer / waiver ≤ source_balance` — پیش از INSERT.
4. `transfer_reversal ≤ remaining_Ti` + `Σ reversals ≤ original.amount`.
5. `period_balance ≥ 0` همیشه (capها + CLAMP).
6. مصرف اعتبار هیچ Payment نمی‌سازد ⇒ revenue تغییر نمی‌کند.
7. as-of در هر D وضعیت اقتصادی همان روز را بازتولید می‌کند (D1/D2).
8. تعهدات تاریخی فیس بی‌صدا تغییر نمی‌کنند (append-only + computed).
9. `current_obligation` / `overdue_debt` / `driver_total_balance` سه aggregate مجزا.

---

## ۷. گردش‌کارهای تراکنش (همه اتمیک، همه با الگوی §۹)

| # | عملیات | گام‌ها |
|---|---|---|
| W1 | **دریافت + تقسیم** | touch Driver → validate → INSERT Payment → از دوره هدف به‌ترتیب تا سقف `balance(period)` شامل بدهی انتقال‌یافته تخصیص می‌یابد؛ دوره‌های متوالی در صورت نیاز تولید می‌شوند تا تمام مبلغ در همان transaction تخصیص یابد. دریافت جدید `CREDIT` نمی‌سازد (D11) |
| W2 | **مصرف اعتبار** | touch Payment منبع → خواندن `source_available` و `target_balance` → `amount ≤ MIN` وگرنه REJECT → INSERT consumption با `consumed_by = مدیر` (C5) |
| W3 | **ابطال پرداخت** | status=`voided` + voided_at/by/reason → reverse همه allocationهای active → reverse همه consumptionهای آن‌ها — **همه با timestamp یکسان `now`**، یک transaction. هیچ DELETE |
| W4 | **اصلاح پرداخت (مبلغ/راننده)** — جدا از W5 (C9) | اصل: status=`corrected` + corrected_at/reason + reverse فرزندان → Payment **جدید** با `correction_of=اصل`، `payment_date=تاریخ واقعی نقد`، `effective_date=روز correction` + allocationهای جدید (effective=روز correction). revenue فقط جدید را می‌شمارد |
| W5 | **اصلاح allocation (دوره اشتباه)** — جدا از W4 | allocation قدیم: reversed_at=now + reason → allocation جدید تحت **همان Payment** با `correction_of=قدیم`، `effective_date=امروز` → trigger جمع. Payment دست‌نخورده؛ **صفر ردیف Payment؛ revenue تغییر نمی‌کند** |
| W5-ext | **اصلاح allocation اعتباری با مصرف‌های وابسته** (D12) | همه در یک transaction با timestamp یکسان: (۱) reverse همه consumptionهای active منبع (بدهی مقصدها بازیابی) → (۲) reverse خود allocation منبع → (۳) جایگزین‌ها (`correction_of`، effective=امروز؛ trigger جمع) → (۴) مصرف‌های جدید **فقط با تأیید مجدد مدیر** (`consumed_by`، effective=امروز). بازاتصال خاموش رکوردهای قدیم به منبع جدید **ممنوع**. سوئیچ هم‌روز as-of: هیچ D هر دو مجموعه را نمی‌بیند. حالت میانی «پیش از تأیید مجدد» واقعی و درست است |
| W6 | **waiver** | `amount ≤ source_balance` وگرنه REJECT → INSERT adjustment |
| W7 | **انتقال** | `T ≤ source_balance` وگرنه REJECT → INSERT transfer |
| W8 | **reversal waiver/transfer** | `Σ previous + R ≤ original.amount`؛ برای transfer اضافه: **`R ≤ remaining_Ti` (پشته)** وگرنه REJECT با پیام هدایت‌گر → INSERT ردیف reversal append-only |
| W9 | **un-settle سپس reversal** (وقتی W8 رد شد) | reverse allocation(های) تسویه مقصد → تخصیص مجدد فقط فیس خود مقصد → W8 در همان transaction → بازتخصیص مانده آزادشده به credit allocation تحت **همان پرداخت اصلی** (قابل ردیابی؛ سابقه است، نه دریافت جدید). credit باید پس از reversal ساخته شود تا مانده انتقال را دوباره تسویه نکند. proof: §۱۱-N4 |
| W10 | **تغییر fee_start_date** | endpoint اختصاصی → محاسبه effective (§۸.۳) → INSERT DriverFeeHistory + UPDATE Driver.fee_start_date، اتمیک |
| W11 | **Refund جزئی/کامل پرداخت** | `PaymentRefund` مستقل با مبلغ/تاریخ/دلیل/کاربر؛ سقف مجموع Refundها = مبلغ پرداخت؛ allocationهای تغییرکرده با reversal و ردیف جایگزین بازسازی می‌شوند؛ درآمد خالص و بدهی دوره از تاریخ effective محاسبه می‌شوند |
| W11 | **تغییر مبلغ فیس** | INSERT FeeSchedule با `effective_from ≥ today`. چیز دیگری لمس نمی‌شود |

---

## ۸. قواعد حسابداری تاریخی و گزارش‌گری

### ۸.۱ Doctrine تاریخ‌ها (D1/D2)
- سه زمان per رکورد: `effective_date` (تجاری — مبنای گزارش‌ها)، `created_at` (حسابرسی)، timestamp رخداد.
- ثبت دیرهنگام نقد واقعی گذشته مجاز (`payment_date` گذشته؛ allocation با effective همان تاریخ).
- correction/void/reversal/تغییر فیس/تغییر era **هرگز backdate** نمی‌شوند.
- Boolean وضعیت ذخیره نمی‌شود ⇒ drift غیرممکن.
- مرز as-of روی **تاریخ محلی** سوئیچ می‌کند (`reversed_at::date ≤ D`)؛ قرارداد صریح.

### ۸.۲ بازسازی دوره‌ها (D3)
- `start_k = add_calendar_months(era_anchor, 3k)`، `end_k = start_{k+1} − 1 day`؛ افزودن ماه تقویمی با clamp روز (31 ژانویه + 3 ماه = 30 آوریل). محاسبه از لنگر ⇒ بدون drift، بدون هم‌پوشانی/شکاف by-construction.
- افق: تا `start ≤ as_of` برای گزارش؛ هدف allocation/consumption فقط دوره‌های `start ≤ today` (پیش‌پرداخت آینده = مسیر credit، C6).
- اعتبار هدف: `(start, end)` باید عضو مجموعه بازسازی‌شده راننده باشد؛ وگرنه 400.

### ۸.۳ قاعده era (D4)
```
effective = ceil_to_grid( max(requested, current_period_end + 1) )
grid = era_anchor + 3k ماه
```
تغییر فقط از مرز دوره بعدی اثر می‌کند؛ دوره‌های آغازشده هرگز تغییر نمی‌کنند؛ allocationهای قدیمی به همان جفت‌تاریخ‌های era قدیم اشاره می‌کنند که همچنان بازسازی می‌شوند.

### ۸.۴ فرمول‌های درآمد نقدی (نسخه نهایی — همه از یک predicate)

| # | گزارش | فرمول |
|---|---|---|
| F1 | درآمد نقدی جاری (تجمعی) | `Σ amount WHERE status='received'` |
| F2 | درآمد نقدی تاریخی as-of D | `Σ amount WHERE valid_as_of(p, D)` |
| F3 | بازه [D1,D2] با دانش امروز | `Σ amount WHERE status='received' AND payment_date ∈ [D1,D2]` |
| F4 | بازه [D1,D2] as-of E | `Σ amount WHERE valid_as_of(p, E) AND payment_date ∈ [D1,D2]`؛ validator `D2 ≤ E` |
| F5a | ثبت دیرهنگام — سمانتیک اقتصادی | `effective_date = payment_date` ⇒ از همان تاریخ نقد در F2/F4 حاضر |
| F5b | ثبت دیرهنگام — سمانتیک حسابرسی | `recorded_as_of` — فقط audit، هرگز با F2 مخلوط نمی‌شود |
| F6 | ابطال/اصلاح پس از تاریخ گزارش | خودکار از timestampها: `> E` ⇒ حاضر در F4؛ `≤ E` ⇒ حذف. در F1/F3 حذف |

### ۸.۵ الزامات گزارش‌گری
- سه aggregate مجزا: `current_obligation`، `overdue_debt` (فقط `end_date < today`)، `driver_total_balance`.
- مانده تفکیکی هر انتقال (`remaining_Ti`) برای ظرفیت reversal.
- `available_credit` قابل ردیابی به رسید منبع؛ `unallocated` به‌عنوان سطل دیدبان (عملیاتاً باید توسط مدیر صفر شود).
- بازتولید as-of برای همه گزارش‌ها؛ Adjustmentها به‌صورت `net_as_of = Σ originals(effective ≤ D) − Σ reversals(effective ≤ D)`.
- گزارش حسابرسی `recorded_as_of` جدا و برچسب‌دار.

---

## ۹. همروندی و یکپارچگی سازگار با SQLite

**واقعیت پایه:** `select_for_update()` روی SQLite بی‌اثر است؛ SQLite در هر لحظه یک نویسنده دارد؛ اولین statement نوشتن قفل RESERVED را تا COMMIT نگه می‌دارد.

**الگوی اجباری هر نوشتن مالی (T1):**
```python
with transaction.atomic():
    # 1) touch: قفل نویسنده همین‌جا گرفته می‌شود (بدون تغییر معنایی)
    Payment.objects.filter(pk=source_id).update(updated_at=timezone.now())
    # 2) validate: خواندن aggregateها — هیچ نویسنده دیگری interleve نمی‌شود
    available = recompute_source_balance(...)
    if requested > available:
        raise ValidationError(...)
    # 3) insert
    AllocationConsumption.objects.create(...)
```
- ترتیب touch ثابت (ریشه Payment/Driver) ⇒ بدون deadlock (T6).
- `timeout=20` موجود؛ تک‌ادمین آفلاین ⇒ contention تقریباً صفر (T7).
- **دفاع عمقی در DB (T2):** triggerهای `BEFORE INSERT/UPDATE` با RunSQL برای (الف) سقف جمع allocation per payment، (ب) موجودی منبع consumption، (ج) جمع cumulative reversal. اسکلت:
```sql
CREATE TRIGGER allocation_cap_insert BEFORE INSERT ON payments_paymentallocation
WHEN NEW.reversed_at IS NULL BEGIN
  SELECT CASE WHEN (SELECT COALESCE(SUM(allocated_amount),0)
                    FROM payments_paymentallocation
                    WHERE payment_id=NEW.payment_id AND reversed_at IS NULL)
                   + NEW.allocated_amount
                   > (SELECT amount FROM payments_payment WHERE id=NEW.payment_id)
  THEN RAISE(ABORT,'allocations exceed payment amount') END;
END;
```
- قیود row-level با `CheckConstraint`؛ خطای trigger/IntegrityError → 400 فارسی (الگوی `drivers/views.py:97-105`).
- `idempotency_key`/`consumption_id` یکتا ⇒ retry امن (T4).
- قرارداد تمام‌AFN ⇒ SUMها دقیقاً integer (T3). (اگر روزی واحد کوچک لازم شد، مهاجرت به integer storage خارج از دامنه فعلی است.)

---

## ۱۰. الزامات محافظت API

1. همه endpointهای مالی `IsAuthenticated` + SessionAuthentication/CSRF. فیلدهای `created_by/reversed_by/...` همیشه از `request.user` — هرگز از client.
2. **هیچ endpoint DELETE** برای رکوردهای مالی؛ admin: `has_delete_permission=False`، فیلدهای مالی/وضعیت read-only؛ `delete()` مدل raise.
3. `DriverSerializer.fee_start_date` **read-only**؛ تغییر فقط `POST /api/drivers/{id}/fee-start-date/` با reason اجباری (W10).
4. تغییر وضعیت فقط via action endpoints: `void/`، `correct/`، `reverse/` — reason اجباری؛ status/reversed در serializer معمولی read-only.
5. اعتبارسنجی هدف: جفت‌تاریخ عضو دوره‌های بازسازی‌شده؛ مبالغ تمام‌AFN و `> 0`; idempotency keyها honor شوند.
6. خطاها → 400 فارسی؛ نقض invariant → 400 با کد مشخص (مثلاً `reversal_exceeds_remaining_transfer`) تا frontend گردش کار W9 را پیشنهاد دهد.

---

## ۱۱. پیوست عددی — همه مثال‌های reconcile‌شده (نسخه رسمی)

**همه مثال‌ها در بازبینی نهایی 2026-11-10 تک‌تک بازمحاسبه و PASS شدند. نسخه قدیمی T5 با cash=700 منسوخ است؛ نسخه رسمی cash=750 است.**

### ۱۱.۱ T5 رسمی (fee=600، T1=300 قدیمی، T2=200، cash=750)

```
obligations(D) = [600, 300, 200]؛ reductions = 750
remaining_own = 0؛ overflow = 150
remaining_T1 = 300 − CLAMP(150, 0, 300) = 150
remaining_T2 = 200 − CLAMP(150−300, 0, 200) = 200
balance(D) = 350
```

| تلاش reversal روی T1 | پشته `R ≤ 150` | cumulative `ΣR ≤ 300` | نتیجه |
|---|---|---|---|
| R=150 | ✓ | ✓ | **ACCEPT** |
| R=200 | ✗ (200 > 150) | ✓ | **REJECT** |
| R=150 دوباره پس از اولی | ✗ (مانده 0) | ✓ (300 ≤ 300) | **REJECT** |
| R=200 پس از R=150 | ✗ | ✗ (350 > 300) | **REJECT** |

پس از R=150: `T1.net=150`؛ بازپشته `[600,150,200]` با reductions=750 ⇒ `remaining_T1=0`، `remaining_T2=200` (دست‌نخورده)، `balance=200`.

| مرحله | S1 (مبدأ T1) | S2 (مبدأ T2) | D (مقصد) | Debt کل | Cash | Debt+Cash=Fees |
|---|---|---|---|---|---|---|
| پس از انتقال‌ها | 300 | 400 | 1100 | 1800 | 0 | 1800 ✓ |
| پس از cash 750 | 300 | 400 | 350 | 1050 | 750 | 1800 ✓ |
| پس از R=150 | 450 | 400 | 200 | **1050 ثابت** | 750 | 1800 ✓ |

قاعده aggregate برای R=200 می‌گفت `200 ≤ 350` و غلط‌تر مجاز می‌کرد؛ پشته رد می‌کند — دلیل وجود §۵.

### ۱۱.۲ T1–T4 (own=600، T=300 مگر ذکر شود)

| مثال | محاسبه | نتیجه |
|---|---|---|
| T1 | cash 300 ⇒ own_rem 300، T_rem 300، bal 600؛ R=300 ≤ 300 ⇒ مقصد 300، مبدأ +300؛ driver: 900+300=1200 | ✓ |
| T2 | cash 600 ⇒ own 0، T_rem 300؛ R=300 ⇒ bal 0 | ✓ |
| T3 | cash 900 ⇒ T_rem 0 ⇒ هر reversal رد (→ W9) | ✓ |
| T4 | توالی A (pay 300 → rev 100) و B (rev 100 → pay 300) هر دو ⇒ own_rem 300، T_rem 200، bal 500؛ مبدأ 400 ⇒ driver 900 + cash 300 = 1200 | ✓ همگرایی |

### ۱۱.۳ C1 / W5-ext (P=700؛ A_fee=400→P1؛ A_cr=300؛ C1=100→P2؛ C2=100→P3؛ فیس هر دوره 600)

| گام | SetCash | Consumed | Avail | Unalloc | Debt (P1/P2/P3) | (O)=1800 | (C)=700 |
|---|---|---|---|---|---|---|---|
| قبل | 400 | 200 | 100 | 0 | 200/500/500=1200 | ✓ | ✓ |
| reverse C1,C2 | 400 | 0 | 300 | 0 | 200/600/600=1400 | ✓ | ✓ |
| reverse A_cr | 400 | 0 | 0 | 300 | 1400 | ✓ | ✓ |
| A′_cr=200 | 400 | 0 | 200 | 100 | 1400 | ✓ | ✓ |
| A_fee2=100→P1 | 500 | 0 | 200 | 0 | 100/600/600=1300 | ✓ | ✓ |
| تأیید مجدد C1′,C2′ | 500 | 200 | 0 | 0 | 100/500/500=1100 | ✓ | ✓ |

gross بعد = 1000 (تاریخی، بی‌ضرر)؛ active = 700 ≤ 700 ✓؛ revenue در همه Dها = 700 ✓؛ سوئیچ هم‌روز as-of ✓. variant credit=100: فقط C1′=100 قابل تأیید؛ P3=600 بازیابی؛ 200 آزادشده به fee/unallocated ⇒ (O)/(C) برقرار ✓.

### ۱۱.۴ N4 — هشت مرحله پایستگی (دو دوره 600؛ TotalFees=1200)

| مرحله | Debt | SetCash | SetCredit | CashRcv | Avail | Consumed | Unalloc |
|---|---|---|---|---|---|---|---|
| 0 شروع | 1200 | 0 | 0 | 0 | 0 | 0 | 0 |
| 1 transfer 300 P1→P2 | 1200 (300/900) | 0 | 0 | 0 | 0 | 0 | 0 |
| 2 receive 900 | 1200 | 0 | 0 | 900 | 0 | 0 | 900 |
| 3 settle P2 با 900 | 300 | 900 | 0 | 900 | 0 | 0 | 0 |
| 4 تلاش R=300 | REJECT (T_rem=0) | — | — | — | — | — | — |
| 5 W9 reverse allocation | 1200 | 0 | 0 | 900 | 0 | 0 | 900 |
| 6 W9 بازتخصیص 600 fee و reversal انتقال | 600 (600/0) | 600 | 0 | 900 | 0 | 0 | 300 |
| 7 بازتخصیص 300 باقی‌مانده به credit | 600 (600/0) | 600 | 0 | 900 | 300 | 0 | 0 |
| 8 consume 300→P1 | 300 | 600 | 300 | 900 | 0 | 300 | 0 |

(O) و (C) در هر ۸ مرحله برقرار؛ مرحله 8 درآمد همچنان 900 ✓.

### ۱۱.۵ مثال‌های Own-First (2A–2C)

- **2A** (fee=600، T=200): cash 250 → bal 550؛ credit 150 → 400؛ waiver 100 → 300؛ cash 150 → 150 (own 0، T_rem 150). ظرفیت reversal = **150** نه 200 ✓. `800 − (400+150+100) = 150` ✓.
- **2B** (fee=600، T=300): waiver 700 ≤ 900 → bal 200؛ waiver-reversal 700 → 900 بازیابی؛ R=300 ≤ 300 → bal 600 ✓.
- **2C** (fee=600، T1=300، T2=200، cash 750): bal 350 (0/150/200)؛ rev T2=200 → 150؛ rev T1=150 → 0؛ R=200 برای T1 رد ✓ — هم‌نسخه با T5 رسمی.

### ۱۱.۶ زنجیره A→B→C (فیس هر دوره 600؛ TotalFees=1800)

| مرحله | عمل | A | B | C | total |
|---|---|---|---|---|---|
| S0 | شروع | 600 | 600 | 600 | 1800 |
| S1 | A→B 300 | 300 | 900 [600, T_AB 300] | 600 | 1800 |
| S2 | B→C 200 | 300 | 700 [own 400, T_AB_rem 300] | 800 [600, T_BC 200] | 1800 |
| S3 | C cash 300 | 300 | 700 | 500 | 1500 (+300=1800) |
| S4 | C cash 500 | 300 | 700 | 0 (T_BC_rem 0) | 1000 (+800=1800) |
| S5 | rev A→B R=300 (≤ T_AB_rem 300 ✓) | 600 | 400 | 0 | **1000 ثابت** |

variant جزئی S5: R=100 ⇒ B=600، A=400، total=1000 ✓؛ تلاش R=250 ⇒ `250 > 200` و cumulative `350 > 300` رد ✓.

**توالی وابستگی‌ساز (downstream-first لازم می‌شود):**

| مرحله | عمل | A | B | C | total |
|---|---|---|---|---|---|
| S1 | A→B 300 | 300 | 900 | 600 | 1800 |
| S2′ | B cash 600 | 300 | 300 [own 0, T_AB_rem 300] | 600 | 1200 (+600) |
| S3′ | B→C 200 | 300 | 100 [reductions 800 ⇒ **T_AB_rem 100**] | 800 | 1200 |
| S4′ | تلاش A→B R=300 | — | **REJECT: 300 > 100** | — | — |
| S5′ | اول rev B→C R=200 (≤ 200 ✓) | 300 | 300 [T_AB_rem 300 بازیافت] | 600 | 1200 |
| S6′ | حالا A→B R=300 ✓ | 600 | 0 | 600 | **1200** (+600=1800) |

### ۱۱.۷ N1–N10 و R1–R3 (خلاصه تأییدشده)

| # | سناریو | نتیجه |
|---|---|---|
| N1 | 700 → 600 fee + 100 credit؛ مصرف 100؛ void زنجیره‌ای | SUM=700 ✓؛ bal 0/500، avail 0 ✓؛ as-of 02-28 revenue=700؛ as-of 03-16 revenue=0، debt 600/600 ✓ |
| N2 | 600/400/300 | need=200، MIN(300,200)=200؛ درخواست 300 رد پیش از درج؛ avail=100 ✓ |
| N3 | transfer 300، reversal جزئی | 300/900→400/800→600/600 ✓؛ 100+250=350>300 رد ✓؛ T=300 > source 200 رد ✓ |
| N4 | reversal پس از تسویه کامل | §۱۱.۴ ✓ |
| N5 | reversal پس از تسویه جزئی | B=500 (T_rem 300)؛ R=300 ✓ → 600/200؛ 800=800 ✓ |
| N6 | void با timestamp | as-of 02-28=800، 03-16=0 ✓ |
| N7 | adjustment جزئی as-of | 300@03-01 − 100@03-10 = 200 در as-of 03-15 ✓ |
| N8 | تغییر فیس 600→700 از 2027-06-01 | دوره 05-09..08-08 ⇒ 600؛ 08-09..11-08 ⇒ 700 ✓ |
| N9 | تغییر era | max(04-01, 05-09)=05-09 روی grid ✓؛ requested 08-01 ⇒ ceil ⇒ 08-09 ✓ |
| N10 | ثبت دیرهنگام | as-of 01-18 debt=100 ✓؛ correction@03-10 در as-of 02-10 نامرئی ✓ |
| R1 | ابطال پس از بازه | F3=0؛ F4@02-28=500؛ F4@04-01=0 ✓ |
| R2 | اصلاح مبلغ 400→800 | as-of 02-28=400؛ 03-15=800؛ جاری=800؛ هیچ D=1200 ✓ |
| R3 | ثبت دیرهنگام 700 | F2@01-18=700 (اقتصادی)؛ F5b@01-18=0 (حسابرسی) ✓ |

---

## ۱۲. برنامه verify یکپارچه V1–V10 — اجرا در فاز ۵ پیاده‌سازی مجاز است

**محیط اجرا:** دیتابیس **موقت ایزوله** (`:memory:` یا فایل tmp / Django test DB). هرگز `backend/db.sqlite3` واقعی؛ هیچ migration روی واقعی تا تأیید نتایج ایزوله.

| # | آزمون | روش / معیار پذیرش |
|---|---|---|
| V1 | rollback اتمیک | در transaction، insert اول موفق، insert دوم عمداً trigger را نقض کند ⇒ assert: count قبل = بعد، هیچ ردیفی نمانده |
| V2 | گرفتن قلمرو نوشتن اولیه | conn1: `atomic()` + touch و نگه‌داشتن؛ conn2: نوشتن ⇒ مسدود تا timeout سپس `OperationalError: database is locked`؛ conn1 سالم commit شود |
| V3a | مصرف همزمان | دو connection هرکدام 200 از موجودی 300 ⇒ دقیقاً یکی موفق؛ نهایت SUM=200، balance=100 |
| V3b | مصرف تکراری | تلاش دوم موجودی به‌روز را ببیند ⇒ reject؛ idempotency_key تکراری ⇒ همان نتیجه اول، بدون ردیف دوم |
| V4 | trigger سقف allocation | INSERT خام SQL که جمع > amount کند ⇒ `RAISE(ABORT)` / IntegrityError؛ بدون ردیف partial |
| V5 | trigger موجودی credit | consumption خام > balance ⇒ abort |
| V6 | trigger cumulative reversal + پشته | reversal خام که جمع > original کند ⇒ abort؛ `R > remaining_Ti` ⇒ reject سرویس (سناریوی رسمی T5: R=150 قبول، R=200 رد) |
| V7 | rollback پس از عملیات ناموفق | سرویس پس از چند نوشتن raise کند ⇒ هیچ orphan row، هیچ timestamp نیمه‌ست |
| V8 | timeout handling | `OPTIONS.timeout` کوچک در test settings؛ قفل بیرونی بیش از timeout ⇒ نگاشت 409/400، بدون commit جزئی؛ retry با idempotency key دقیقاً یک‌بار اثر کند |
| V9 | بازتولید as-of | seed با تاریخ‌های معلوم؛ F2/F4 و پشته Own-First در Dهای مختلف ⇒ مقادیر مورد انتظار پیوست §۱۱ (شامل T5 رسمی 750) |
| V10 | parity سرویس/trigger | یک invariant هم از مسیر ORM سرویس و هم raw SQL نقض شود ⇒ هر دو رد |

---

## ۱۳. ترتیب migration و پیاده‌سازی — در حال اجرا (اجازه 2026-11-10)

| فاز | محتوا | دروازه |
|---|---|---|
| 0 | اجازه کتبی پیاده‌سازی از کاربر | **اجازه کتبی — صادر شد (2026-11-10)** |
| 1 | backup (`scripts/backup-db.sh`) → FeeSchedule + DriverFeeHistory + data migration (ردیف 600؛ backfill era اولیه) — verify روی **کپی** دیتابیس | تأیید نتیجه کپی |
| 2 | Payment + PaymentAllocation + CheckConstraintها + trigger سقف | تست invariant روی کپی |
| 3 | AllocationConsumption + trigger موجودی منبع | همان |
| 4 | Adjustment + trigger cumulative reversal | همان |
| 5 | سرویس‌های اتمیک (§۷) + endpointها + read-only guards (§۱۰) | مرور API |
| 6 | frontend (ثبت رسید، مصرف اعتبار، گزارش‌های سه‌گانه) | تست دستی کاربر |
| 7 | مجموعه تست invariantها (V1–V10؛ اجرا روی دیتابیس ایزوله) | گزارش نهایی |

---

## ۱۴. پرسش‌های فنی حل‌نشده (غیرمسدودکننده)

هیچ پرسش **تجاری/حسابداری** باز نمانده است. موارد فنی زیر در مرور پیاده‌سازی ratify می‌شوند:

1. ratify نهایی قرارداد تمام‌AFN (T3) و `receipt_number` اختیاری/غیر-unique (T5).
2. متن نهایی DDL triggerها متناسب با نسخه SQLite مستقر (اسکلت §۹ طرح است).
3. استراتژی ایندکس/caching بازسازی دوره‌ها پس از اندازه‌گیری واقعی (T8).
4. نهایی‌سازی فهرست کدهای خطا (مثلاً `reversal_exceeds_remaining_transfer`).
5. earmark درون-دوره اگر روزی لازم شد ⇒ توسعه آینده `ledger.application` (خارج از دامنه؛ C10 فعلاً آن را نمی‌خواهد).
6. UX گزارش‌های سه‌گانه و نمایش `remaining_Ti` در frontend (فاز ۶).

---

## ۱۵. بیانیه وضعیت نهایی

1. **Own-First در سراسر این سند `CONFIRMED — FINAL BUSINESS RULE` است** (§۱-C10، §۵، §۷-W8، §۱۱). هیچ جای این سند آن را proposed/unapproved توصیف نمی‌کند؛ اشاره به وضعیت پیشین PROPOSED فقط به‌عنوان تاریخچه منسوخ در §۲.۱ آمده است.
2. **T5 رسمی از cash=750 استفاده می‌کند** (balance=350؛ T1_rem=150؛ R=150 ACCEPT، R=200 REJECT). نسخه 700 منسوخ است و هیچ‌جای این سند آن را رسمی نمی‌داند.
3. **همه مثال‌های عددی reconcile شده‌اند** (§۱۱)؛ هیچ قانون تجاری متعارض باقی نمانده است.
4. **پیاده‌سازی کامل اجازه داده شده است (AUTHORIZED — 2026-11-10).** کاربر پیاده‌سازی کامل ماژول مالی (مدل‌ها، migrationها، frontend، منطق مالی و API، تکمیل دیتابیس مشروط به backup و verify اجباری) را صریحاً مجاز دانست. فازهای §۱۳ و برنامه V1–V10 §۱۲ مطابق دستورالعمل شش‌فازی کاربر اجرا می‌شوند: backup اول، migration روی کپی ایزوله، تست‌ها روی دیتابیس ایزوله، سپس اعمال روی دیتابیس اصلی با backup به‌عنوان نقطه بازیابی.