Ниже приведён список конкретных багов в коде проекта (от падений с `HTTP 500` и гонок данных до ошибок в бизнес-логике и UI), которые нужно исправить.

---

### 1. Критические баги (падения 500, гонки транзакций, зависания статусов)

1. **Повреждённая (бинарная) кодировка 3 файлов бэкенда**
* **Где:** `backend/users/models.py`, `backend/validation/mesh.py`, `backend/integrations/auth.py`.


* **В чём баг:** В репозитории эти три файла сохранены как бинарные (вероятно, UTF-16 или с нулевыми байтами). Из-за этого падает `flake8` в CI (`E902`), не работают Git-диффы и возможны ошибки импорта в Linux-контейнере.





2. **Гонка транзакций (`@transaction.atomic` + `django-rq`) — задачи уходят в воркер до коммита в БД**
* **Где:** `backend/orders/services.py` (`post_message`) и `backend/notifications/services.py` (`notify`).


* **В чём баг:** Функции `notify()` и `enqueue_process()` вызываются внутри блока `@transaction.atomic`. Когда `TASKS_SYNC=False` (в Docker), `django-rq` мгновенно кладёт задачу в Redis до завершения транзакции PostgreSQL. Воркер в соседнем контейнере читает БД раньше коммита: `Notification.objects.filter(pk=notification_id).first()` возвращает `None`, воркер выходит (`if not n: return`), и письмо навсегда зависает в статусе `PENDING`, а `process_order` видит старый статус заказа (`CLARIFICATION` вместо `NEW`).




3. **Заказ навсегда зависает в `CLARIFICATION`, если загрузить модель через `POST /api/orders/{id}/model**`
* **Где:** `backend/orders/services.py` (`attach_model`, `process_order`) и `backend/orders/views.py` (`ModelUpload.post`).


* **В чём баг:** Метод `attach_model` разрешает загрузку модели в статусах `DRAFT` и `CLARIFICATION` (`if order.status not in (S.DRAFT, S.CLARIFICATION)`), после чего `ModelUpload` вызывает `enqueue_process(o.pk)`. Но переход `CLARIFICATION -> NEW` в `ModelUpload`/`attach_model` **не вызывается** (он есть только в `post_message`). В итоге `process_order` проверяет `if order.status == S.NEW:`, видит `CLARIFICATION` и ничего не делает — заказ остаётся висеть в `CLARIFICATION`.


4. **Не пересчитываются проверка (`ValidationResult`) и цена (`Quote`) при загрузке модели через чат в `DRAFT` и `MANUAL_REVIEW**`
* **Где:** `backend/orders/services.py` (`post_message`).


* **В чём баг:** В `post_message` разрешено приложить файл модели в статусах `DRAFT`, `CLARIFICATION` и `MANUAL_REVIEW`. Но `enqueue_process(order.pk)` вызывается **только** внутри ветки `if order.status == S.CLARIFICATION:`. Если клиент или менеджер загрузит новую модель через сообщения в `DRAFT` или `MANUAL_REVIEW`, новая `ModelVersion` станет `is_current=True`, но для неё не создастся `ValidationResult` (`validation` станет `null`) и не пересчитается `Quote`.


* **Что править:** Если `mv is not None`, вызывать `enqueue_process(order.pk)` также для `DRAFT` и `MANUAL_REVIEW`.




5. **Падение с `HTTP 500` при корректировке цены (`POST /api/orders/{id}/adjustment`) и при оплате**
* **Где:** `backend/pricing/services.py` (`apply_adjustment`, `QuoteError`), `backend/orders/views.py` (`OrderAdjustment.post`), `backend/orders/services.py` (`pay`, `decision`).


* **В чём баг:**
* В `OrderAdjustment.post` сумма приводится к `float(request.data.get('adjustment'))`, а затем в `apply_adjustment` передаётся в `Decimal(adjustment)` (из `float` получается `Decimal('-50.10000000000000142...')`, что ломает сохранение в `DecimalField(decimal_places=2)`).


* Если скидка больше суммы заказа (`new_total < 0`), срабатывает SQL-ограничение `quote_total_gte_0` и сервер падает с необработанным `IntegrityError` (**HTTP 500**).


* Если заказ попал в `MANUAL_REVIEW` без расчёта (`current_quote(order)` равен `None`), вызов `apply_adjustment` выбрасывает `QuoteError`, который не наследуется от `DomainError` и не ловится в `api_exception_handler` — снова **HTTP 500**.


* Если такой заказ без `Quote` менеджер одобрит (`MANUAL_REVIEW -> CHECKED -> AWAITING_PAYMENT`), то в `decision()` (при `PAY_STUB_ENABLED=False`) и в `pay()` обращение к `quote.total` упадёт с `AttributeError: 'NoneType' object has no attribute 'total'` (**HTTP 500**).




* **Что править:**
* Наследовать `QuoteError` от `DomainError` (или бросать `DomainError`).


* Парсить `adjustment` через `Decimal(str(request.data.get('adjustment')))` и проверять `if new_total < 0: raise DomainError('Итоговая сумма не может быть отрицательной.')`.


* Запретить переход `MANUAL_REVIEW -> CHECKED` и `CHECKED -> AWAITING_PAYMENT` в `orders/services.py`, если `current_quote(order) is None`.






6. **Падение `GET /health`, если подключить готовую вьюху из `config/views.py**`
* **Где:** `backend/config/urls.py` и `backend/config/views.py`.


* **В чём баг:** В `config/urls.py` написана заглушка `health`, которая всегда возвращает HTTP 200 (даже при упавшей БД) и вообще не проверяет Redis. При этом рядом лежит файл `config/views.py` с нормальной проверкой БД и Redis, но он не импортирован в `urls.py`, а внутри него написано `if not settings.RQ_SYNC:` вместо `if not settings.TASKS_SYNC:` (при вызове упадёт с `AttributeError`). Также файл `backend/config/errors.py` полностью дублирует `backend/config/exceptions.py` и нигде не используется.


* **Что править:** В `config/views.py` заменить `settings.RQ_SYNC` на `settings.TASKS_SYNC`, подключить `config.views.health` в `config/urls.py`, а мёртвый `config/errors.py` удалить.





---

### 2. Логические баги в валидации, расчёте и планировании принтеров

7. **Ошибка `E-04` перекрывает `E-06` (баг на эталонном тесте `P-05`)**
* **Где:** `backend/validation/services.py` (`validate`) и `backend/scheduling/services.py` (`fits_any_active`).


* **В чём баг:** В `validate()` сначала проверяется:
```python
if tech and not issues and not scheduling_services.fits_any_active(technology=tech, bbox=bbox):
    issues.append(_issue('E-04', ...))

```


А `fits_any_active` ищет принтеры с фильтром `status=Printer.Status.ACTIVE`. Когда в тесте `P-05` единственный принтер `DMLS-01` переводится в `RETIRED`, список активных принтеров `DMLS` пуст, `fits_any_active` возвращает `False`, и система выставляет ошибку габаритов **`E-04`** (хотя деталь 40×40×40 мм легко помещается в принтер 250×250×300 мм), а до проверки **`E-06`** код вообще не доходит из-за `and not issues`. В `test_pricing_parity.py` этот баг замаскирован костылём `assert 'E-04' in codes or 'E-06' in codes`.


* **Что править:** В `fits_any_active` (или отдельной функцией `fits_any_printer_of_tech`) проверять габариты по принтерам технологии (либо выдавать `E-04` только если в технологии есть принтеры, но ни один не вмещает `bbox`), а отсутствие активного доступного принтера фиксировать кодом `E-06`. Также убрать `and not issues` перед проверкой `E-06`, чтобы коды ошибок не скрывали друг друга.




8. **Неверный расчёт специализации `LARGE` и штрафа `K_спец = 24 ч**`
* **Где:** `backend/scheduling/services.py` (`required_specialization`).


* **В чём баг:**
```python
plain = Printer.objects.filter(technology=technology, status=Printer.Status.ACTIVE).exclude(
    specialization=Printer.Specialization.LARGE)
if bbox and not any(fits(p.dims_sorted, bbox) for p in plain):
    return Printer.Specialization.LARGE

```


* Во-первых, `.exclude(specialization=LARGE)` оставляет в выборке другие специализированные принтеры (например, `SLA-HS` со специализацией `HIGH_STRENGTH_RESIN`), хотя по спецификации нужно проверять, помещается ли модель в принтер **без специализации** (`specialization=Printer.Specialization.NONE`).


* Во-вторых, из-за фильтра `status=ACTIVE`, если обычные принтеры (`FDM-01`, `FDM-02`) временно переведены в `MAINTENANCE`, `plain` становится пустым, и любая мелкая деталь `10x10x10` мм ошибочно получает требование `LARGE`, из-за чего с `FDM-XL` снимается штраф `24 ч` за использование крупногабаритного принтера.




* **Что править:** Искать обычные принтеры по `specialization=Printer.Specialization.NONE` (без фильтра `status=ACTIVE`, так как физический типоразмер детали не зависит от того, на ТО ли сейчас принтер), и возвращать `LARGE` только если деталь реально больше обычных принтеров, но помещается в `LARGE`-принтер.




9. **Принтер считается занятым во время `POST_PROCESSING`, а переназначение заказа учитывает заказ дважды**
* **Где:** `backend/scheduling/services.py` (`ACTIVE_ORDER_STATUSES`, `_t_free_hours`, `_last_material`, `equipment_load`).


* **В чём баг:**
* В `ACTIVE_ORDER_STATUSES = ('DISTRIBUTED', 'PRINTING', 'POST_PROCESSING')` включён статус `POST_PROCESSING`. Когда деталь уже напечатана и ушла на шлифовку/покраску (`POST_PROCESSING`), 3D-принтер свободен, но код продолжает считать его занятым в `_t_free_hours` и `equipment_load`.


* Когда менеджер нажимает «Переназначить» для заказа в статусе `DISTRIBUTED`, функция `recommendation(order)` вызывает `_t_free_hours`, которая суммирует **текущее назначение этого же заказа**, завышая время ожидания `t_free` и `score` текущего принтера на время печати самого заказа.


* Функция `_last_material(printer)` выбирает последнее назначение `Assignment.objects.filter(printer=printer, is_current=True)` **без фильтра по статусу заказа**. Если заказ в статусе `DISTRIBUTED` был отменён (`CANCELLED`), его `Assignment.is_current` остаётся `True`, и планировщик начисляет штраф `2 ч` за смену материала от отменённого заказа.




* **Что править:**
* Убрать `'POST_PROCESSING'` из `ACTIVE_ORDER_STATUSES`.


* При отмене заказа (`transition` в `CANCELLED`) сбрасывать `Assignment.objects.filter(order=order, is_current=True).update(is_current=False)`, а в `_last_material` исключать `order__status__in=('CANCELLED', 'REJECTED')`.


* В `recommend()` и `_t_free_hours()` передавать `exclude_order=order`, чтобы при переназначении заказ не конкурировал сам с собой в очереди.






10. **Планировщик игнорирует настройки активного тарифа `TariffVersion.params**`
* **Где:** `backend/scheduling/services.py` (`HORIZON_HOURS`, `recommend`, `equipment_load`).


* **В чём баг:** В БД в `TariffVersion.params` хранятся `printer_hours_per_day`, `horizon_days`, `k_change`, `k_spec`. Но `scheduling/services.py` их вообще не читает: в коде зашиты константы `HORIZON_HOURS = 140.0`, `change = 2`, `spec_pen = 24`. Если администратор поменяет тариф в админке, распределение и расчёт загрузки не изменятся.


* **Что править:** Получать параметры через `pricing.services.get_tariff_params()` и подставлять `k_change`, `k_spec` и `horizon_days * printer_hours_per_day`.





---

### 3. Баги в API, валидации входных данных и админке

11. **Необработанные исключения (`HTTP 500`) при некорректных данных в `PATCH /api/orders/{id}` и `GET /api/orders**`
* **Где:** `backend/orders/services.py` (`update_draft`) и `backend/orders/views.py` (`OrderListCreate.get`).


* **В чём баг:**
* В `update_draft`: передача `desired_date: ""` (пустая строка из `<input type="date">`), `quantity: "abc"` или `quantity: null`, `delivery_address: null`, либо несуществующего UUID материала/технологии приводит к `ValueError` / `TypeError` / `IntegrityError` (**HTTP 500**).


* Функция `desired_date_ok(d)` написана в конце `orders/services.py`, но нигде не вызывается — можно поставить желаемую дату в 2020 году.


* В `OrderListCreate.get`: передача `?page=abc` или `?priority=abc` роняет сервер с `ValueError` (**HTTP 500**).


* В `update_draft` вызов `process_order(order.pk)` выполняется **синхронно** в HTTP-потоке вместо `enqueue_process(order.pk)`.




* **Что править:** Добавить валидацию типов и проверку `desired_date_ok` в `update_draft` (конвертировать пустую строку `desired_date` в `None`, проверять существование и `is_active` справочников), обернуть `int()` в `try/except`, и заменить прямой вызов `process_order` на `enqueue_process`.




12. **Сбой генерации номера заказа `_new_number()` после 50 заказов или на границе суток UTC/MSK**
* **Где:** `backend/orders/services.py` (`_new_number`).


* **В чём баг:**
```python
today = timezone.localdate()
base = Order.objects.filter(created_at__date=today).count() + 1
for i in range(base, base + 50): ...

```


Если за день часть черновиков или заказов создавалась на стыке часовых поясов, либо в цикле накопились сдвиги номеров, после 50 итераций метод выбрасывает `Не удалось сформировать номер заказа.`.


* **Что править:** Искать максимальный существующий номер по префиксу `Order.objects.filter(number__startswith=f'3DP-{today:%y%m%d}-').order_by('-number').first()`, парсить последний индекс `int(last.number.split('-')[-1]) + 1`.




13. **В карточке заказа менеджера отображаются взаимоисключающие кнопки смены статуса (приводящие к `409 Conflict`)**
* **Где:** `backend/orders/serializers.py` (`available_transitions`) и `frontend/src/pages/manager/OrderReview.tsx`.


* **В чём баг:** Функция `available_transitions` возвращает все переходы из словаря `TRANSITIONS` без учёта условий `_guard`:
* В статусе `PRINTING` менеджеру одновременно рисуются кнопки `→ Постобработка` и `→ Готов к выдаче`, хотя одна из них всегда запрещена и при нажатии возвращает ошибку `409`.


* В статусе `PAID` в блоке «Смена статуса» рисуется кнопка `→ Распределён`, нажатие на которую без назначения принтера всегда выдаёт `409 Сначала назначьте принтер.` (хотя само назначение принтера блоком выше автоматически переводит заказ в `DISTRIBUTED`).




* **Что править:** В `available_transitions` фильтровать переходы с учётом состояния заказа: из `PRINTING` отдавать `POST_PROCESSING` только если `o.post_processings.exists()`, иначе `READY`; из `PAID` не отдавать ручную кнопку `DISTRIBUTED`, если нет `current_assignment(o)`.




14. **Интеграционный API (`GET /api/integration/orders`) не возвращает модель, принтер, цех и параметры печати**
* **Где:** `backend/integrations/views.py` (`IntegrationOrders.get`, `ExportOrders.get`).


* **В чём баг:** По спецификации (`F-INT-01`, Таблица 24) метод `GET /api/integration/orders` должен отдавать инженерному модулю заказы в статусах `PAID..READY` **с моделью, параметрами (технология, материал, качество, цвет, постобработка), назначенным принтером/цехом и историей согласования**. Сейчас он возвращает урезанный `summary(o)`, где нет ни модели, ни качества, ни цвета, ни постобработки, ни принтера с цехом. А `POST /api/integration/orders/{id}/status` принимает `actual_print_hours` и `actual_mass_g`, но не сохраняет их в поля модели заказа/назначения (они теряются для выгрузки `GET /api/integration/export/orders`).


* **Что править:** Добавить поля `actual_print_hours` и `actual_mass_g` в `Order` (или `Assignment`), возвращать в `IntegrationOrders` полный DTO (с моделью, параметрами и назначением) и включить фактические показатели в `ExportOrders`.




15. **Отсутствует запись в `AuditLog` при изменении справочников и тарифов в админке, а `Material`, `Printer` и `Workshop` можно удалить**
* **Где:** `backend/catalog/admin.py` и `backend/pricing/admin.py`.


* **В чём баг:**
* Таблица `AuditLog` никогда не заполняется при редактировании справочников и тарифов в `/admin/` (нарушены `U-A-11`, `F-CORE-04`, `F-MGR-10`, `S-SEC-07`).


* `MaterialAdmin`, `PrinterAdmin` и `Workshop` не унаследованы от `NoDeleteAdmin` — администратор может попытаться удалить их в `/admin/`.




* **Что править:** Унаследовать все админ-классы каталога и тарифов от общего базового класса `AuditedNoDeleteAdmin`, который запрещает `has_delete_permission` и в `save_model` пишет `AuditLog` с `before` и `after`.




16. **Повторная отправка писем (`retry_due_emails`) никогда не запускается автоматически**
* **Где:** `backend/notifications/services.py`.


* **В чём баг:** При ошибке SMTP уведомлению выставляется `delivery_status = 'RETRY'` и `next_attempt_at` (+5, +15, +60 мин), но команда `python manage.py retry_notifications` нигде не вызывается ни воркером, ни кроном.


* **Что править:** Либо планировать отложенную задачу в `django-rq` (`queue.enqueue_in(timedelta(minutes=...), send_email_notification, str(n.id))`), либо запускать периодический цикл проверки в контейнере `worker`.





---

### 4. Баги во Frontend (`React / TypeScript`)

17. **При ошибке загрузки `E-01` на шаге 1 в базе остаётся мусорный заказ в статусе `CANCELLED**`
* **Где:** `frontend/src/pages/NewOrder.tsx` (`upload`).


* **В чём баг:** Когда клиент загружает первый файл на шаге 0, `upload()` **сначала** делает `POST /api/orders` (создаёт черновик в БД), а затем загружает файл. Если файл имеет неверный формат (`.step`, ошибка `E-01`) или размер > 50 МБ, блок `catch` вызывает `POST /api/orders/{id}/cancel`. Это переводит пустой черновик в статус `CANCELLED`, и у клиента в списке «Мои заказы» появляются пустые отменённые заказы, хотя по требованию `E-01` (Таблица 18 спецификации) **заказ вообще не должен создаваться**.


* **Что править:** Проверять расширение (`.stl`, `.obj`, `.3mf`) и размер файла (`<= 50 МБ`) на клиенте до вызова `POST /api/orders`, а на бэкенде при отмене пустого черновика (`status == 'DRAFT'` без модели) удалять черновик или скрывать пустые черновики.




18. **Потеря клика по кнопке «Далее» при вводе адреса доставки, количества или комментария (`onBlur` блокирует кнопку)**
* **Где:** `frontend/src/pages/NewOrder.tsx` (шаги 1 и 2).


* **В чём баг:** Поля «Количество копий», «Адрес доставки» и «Комментарий» отправляют `patch(...)` на событие `onBlur`. Когда пользователь вводит адрес доставки и сразу нажимает кнопку «Далее», по событию `mousedown` срабатывает `onBlur` у инпута -> вызывается `patch()` -> ставится `setBusy(true)` -> кнопка «Далее» (`disabled={!canNext || busy}`) мгновенно блокируется до наступления `mouseup`/`click`, и переход на следующий шаг не срабатывает с первого клика.


* **Что править:** Не блокировать навигацию по шагам во время фонового `onBlur`-сохранения либо сохранять `address`, `quantity` и `comment` при нажатии «Далее».




19. **Резервная загрузка 3D-модели в `ModelViewer.tsx` не учитывает `VITE_API_URL**`
* **Где:** `frontend/src/components/ModelViewer.tsx` (`fetchBuffer`) и `backend/orders/views.py` (`ModelFile.get`).


* **В чём баг:** Если прямая ссылка MinIO (`info.url`) недоступна из-за CORS, `ModelViewer` делает `fetch(info.download_url, { credentials: 'include' })`, где `download_url = '/api/orders/{id}/model/{v}/download'`. Если фронтенд запущен без прокси с `VITE_API_URL=http://localhost:8000/api` (как указано в разделе 10 `3DPRINT_SPEC_FOR_CLAUDE.md`), запрос уйдёт на `http://localhost:5173/api/...` и вернёт 404. Кроме того, для `3MF` и `OBJ` в `ModelViewer.tsx` не вызывается `computeVertexNormals()` для дочерних `Mesh`, если в файле нет нормалей.


* **Что править:** Формировать URL скачивания через базовый `BASE` из `api/client.ts` и вызывать `computeVertexNormals()` при обходе мешей `OBJ`/`3MF`.




20. **Отсутствуют сортировка заказов, управление приоритетом и поле `desired_date` в UI**
* **Где:** `frontend/src/pages/manager/Queue.tsx`, `frontend/src/pages/manager/OrderReview.tsx`, `frontend/src/pages/NewOrder.tsx`, `backend/orders/views.py`.


* **В чём баг:**
* В `Queue.tsx` есть фильтр по приоритету (`priority`), но нигде в UI и API менеджера нельзя изменить приоритет заказа (у всех заказов навсегда `priority = 0`).


* В `Queue.tsx` и `OrderListCreate.get` нет сортировки очереди заказов (`ordering` всегда жестко `-created_at`), хотя требование `U-M-14` / `F-MGR-01` требует сортировку по статусу, срочности, материалу, цеху и дате.


* В `NewOrder.tsx` нет поля выбора желаемой даты (`desired_date`) и предупреждения о том, что единицы измерения модели — миллиметры (`S-DOM-06`).




* **Что править:** Добавить параметр `ordering` в `OrderListCreate.get` и селект сортировки в `Queue.tsx`, добавить переключатель приоритета в `OrderReview.tsx`, а в `NewOrder.tsx` — инпут `desired_date` и подсказку про миллиметры.




21. **Падение CI во Frontend и неполные тесты в Backend**
* **Где:** `.github/workflows/ci.yml`, `frontend/package-lock.json`, `backend/tests/test_pricing_parity.py`.


* **В чём баг:**
* В `.github/workflows/ci.yml` выполняется `npm ci`, который гарантированно падает, так как в `frontend/` отсутствует `package-lock.json`.


* В `backend/tests/test_pricing_parity.py` написано только 8 из 24 типовых тестовых заказов из Приложения В (`T-05..T-10`, `T-12`, `T-14..T-18`, `T-20`, `T-22..T-24` пропущены).




* **Что править:** Сгенерировать и закоммитить `frontend/package-lock.json`, а в `test_pricing_parity.py` добавить оставшиеся 16 кейсов из Таблицы 35.





---

Если нужно, могу сразу выдать готовые патчи кода для самых опасных мест (`orders/services.py`, `validation/services.py`, `scheduling/services.py`, `pricing/services.py` и `test_pricing_parity.py`). С какого модуля начнём?