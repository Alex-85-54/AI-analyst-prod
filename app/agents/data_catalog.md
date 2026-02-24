# ДАТА-КАТАЛОГ: КЛИЕНТЫ (CLIENTS)

| Таблица | Назначение | Основные поля |
|---------|------------|---------------|
| **clients** | Основной профиль клиента | shop_id, email, phone, first_name, last_name, birthday, gender, loyalty_id, telegram_id, fb_id, vk_id, web_push_enabled, mobile_push_enabled, accepted_subscription |
| **client_emails** | Email-адреса клиентов | client_id, email, created_date |
| **client_phones** | Номера телефонов клиентов | client_id, phone, created_at |
| **client_properties** | Кастомные свойства клиентов (EAV) | client_id, key, value, json_value |
| **client_property_keys** | Справочник кастомных свойств | shop_id, key, name, property_type, is_public |
| **client_tags** | Связь клиентов с тегами | client_id, tag_id |
| **client_wishes** | Избранное / список желаний | client_id (PK), items (array) |
| **client_calls** | История звонков с клиентами | client_id, call_type, call_event, call_theme, comment |
| **client_communications** | История незвонковых коммуникаций | client_id, comment, status, author_name |
| **client_best_email_times** | Оптимальное время отправки email | client_id, hour, calculated_at |
| **client_errors** | Ошибки на стороне клиента | shop_id, exception_class, exception_message, resolved |
| **client_metrics** | RFM-метрики и LTV | client_id, orders_total, frequency, recency, ltv, aov, ltv_predicted |
| **property_calculates** | Кэш расчетных свойств | client_id, property |
| **cltv** | Пожизненная ценность клиента | client_id, cltv |
| **device_clients** | Связь устройств с клиентами | code (device), client_id |
| **web_push_tokens** | Токены для web-push уведомлений | client_id, token, browser, did |
| **mobile_push_tokens** | Токены для мобильных push | client_id, token, platform, did |
| **last_queries** | История поисковых запросов клиента | client_id, category_id, locale, queries (array) |
| **client_unsubscribes** | Отписки от рассылок | shop_id, channel_type, channel_id, message_type |
| **client_unsubscribe_events** | События отписки клиентов | shop_id, channel_type, channel_id, message_type, event, date |
| **profile_events** | События обогащения профиля клиента | client_id, did, sid, shop_id, event, industry, property, value |
| **subscription_logs** | Полная история подписок и отписок | shop_id, client_id, contact_type, contact_value, campaign_type, event, channel, ip |

---

# ДАТА-КАТАЛОГ: ЗАКАЗЫ (ORDERS)

| Таблица | Назначение | Основные поля |
|---------|------------|---------------|
| **orders** | Основная таблица заказов | shop_id, uniqid, client_id, date, value, status, utm, stream, payment_type, delivery_type, promocode, offline |
| **order_items** | Товары в заказе | order_id, item_id, item_uniqid, amount, price, discount, recommended_by, recommended_code, segment, brand, categories, line_id |
| **order_histories** | История изменений заказа | order_id, status, payment_method, delivery_method, common_value |
| **order_statuses** | Маппинг внешних статусов заказов | shop_id, status (внешний), internal_status |
| **order_property_keys** | Справочник кастомных свойств заказов | shop_id, key, name, property_type |
| **order_property_values** | Значения кастомных свойств заказов | order_id, key, value_string, value_integer, value_date |
| **loyalty_orders** | Данные заказов в программе лояльности | uniqid, identifier, discounts, promo_codes, certificates, referrer_identifier |
| **nps_reviews** | NPS-оценки и отзывы к заказам | order_id, client_id, rate, comment, nps_category_id |
| **reputations** | Отзывы на товары/заказы | entity_id, entity_type, rating, plus, minus, comment |
| **order_source_events** | Атрибуция заказов по источникам | shop_id, client_id, source_type, source_code, source_id |
| **orders_see_also** | Совместные покупки для рекомендаций | shop_id, order_id, items (array), date |

---

# ДАТА-КАТАЛОГ: ТОВАРЫ (ITEMS)

| Таблица | Назначение | Основные поля |
|---------|------------|---------------|
| **items** | Основной каталог товаров | shop_id, uniqid, name, price, is_available, brand, category_ids, location_ids, tags, sales_rate, url, image_url |
| **item_categories** | Категории товаров (иерархия) | shop_id, external_id, name, parent_id, parent_external_id, url, is_available |
| **categories** | Упрощенный справочник категорий | shop_id, name, code, increase_units, increase_rubles |
| **product_parameters** | Параметры/характеристики товаров | shop_id, name, unit, values (jsonb) |
| **product_collections** | Динамические подборки товаров | shop_id, name, groups (jsonb rules), aasm_state |
| **product_collection_templates** | Шаблоны отображения подборок | shop_id, name, template |
| **product_counters** | Счетчики популярности товаров | shop_id, uniqid, daily_view, daily_cart, daily_purchase, now_view |
| **product_profits** | Прибыль по товарам | shop_id, uniqid, profit |
| **subscribe_for_product_availables** | Подписки на наличие товара | client_id, item_uniqid, subscribed_at |
| **subscribe_for_product_prices** | Подписки на снижение цены | client_id, item_uniqid, price, subscribed_at |
| **merchants** | Продавцы/мерчанты | shop_id, name |

---

# ДАТА-КАТАЛОГ: МАРКЕТИНГОВЫЕ КАМПАНИИ (CAMPAIGNS)

| Таблица | Назначение | Основные поля |
|---------|------------|---------------|
| **bulk_campaigns** | Массовые рассылки | shop_id, channel, name, subject, state, segment_ids, exclude_segment_ids, started_at, finished_at, statistic, ab_test |
| **campaign_recipients** | Получатели массовых рассылок | bulk_campaign_id, client_id, status, attempts, best_hour, worker_id, next_try_at |
| **bulk_messages** | События массовых рассылок | shop_id, bulk_campaign_id, client_id, code, event, channel, uid, date |
| **bulk_click_maps** | Клики по картам ссылок в рассылках | shop_id, bulk_campaign_id, client_id, code, position, sign |
| **chains** | Маркетинговые цепочки/автоворонки | shop_id, name, enabled, rules, draft_rules, position, test_mode |
| **chain_messages** | События цепочек писем | shop_id, chain_id, client_id, code, event, channel, rule_id, date |
| **chain_works** | Отложенные работы цепочек | chain_id, client_id, rule_id, delayed_to, args |
| **chain_delay_messages** | Отложенные сообщения цепочек | chain_id, client_id, channel, delayed_to, body, subject, rule, args |
| **chain_templates** | Шаблоны сообщений для цепочек | shop_id, channel, name, liquid_template, subject, utm, promo_code_list_id |
| **chain_channel_sends** | Факты отправок в цепочках | client_id, chain_id, channel, date |
| **cancelled_chain_runs** | Отмененные цепочки | shop_id, chain_id, client_id, rule_id, reason, date |
| **chain_skips** | Пропущенные шаги в цепочках | shop_id, client_id, chain_id, chain_skip_id, event_skip, date |
| **transactional_mailings** | Транзакционные письма | shop_id, code, name, subject, template, channel, enabled |
| **transactional_messages** | События транзакционных писем | shop_id, campaign_id, client_id, code, event, channel, uid, date |
| **popups** | Всплывающие окна | shop_id, name, popup_type, rules, channels, components, promo_code_list_id |
| **popup_events** | События попапов | shop_id, popup_id, client_id, did, sid, event, channel, date |
| **stories** | Stories (истории) | shop_id, name, subject, avatar, status, active_from, active_to, duration |
| **story_blocks** | Блоки историй | shop_id, name, code, rules, theme_id |
| **story_slides** | Слайды историй | story_id, name, background, elements, duration, position |
| **story_events** | События историй | shop_id, story_id, story_slide_id, client_id, event, sid, code, date |
| **recommender_blocks** | Блоки рекомендаций | shop_id, code, name, rules, limit, template, test_mode |
| **recommender_block_requests** | Запросы к блокам рекомендаций | shop_id, recommender_block_id, client_id, recommendations_count, recommendations_time, segment, platform |
| **recommender_block_connected** | Сводка последних запросов к блокам | date, shop_id, recommender_block_id, max(created_at) |
| **recommender_templates** | Шаблоны рекомендаций | shop_id, name, template |
| **recommender_reports_table** | Технические отчеты рекомендателя | shop_uniqid, recommender_block_uniqid, duration, error_code, server_ip |
| **sliders** | Слайдеры на сайте | shop_id, code, name, width, height |
| **slider_events** | События слайдеров | shop_id, slider_id, banner_id, client_id, event, sid, did, stream, date |
| **marketing_activities** | План-факт маркетинга | name, date, expenses, clicks, qualified_leads, mrr |
| **also_viewed** | Совместные просмотры товаров | shop_id, client_id, items (array), date |
| **bounces** | Отказы писем | shop_id, source_type, source_id, client_id, code, bounce_reason, diagnostic_code, email |

---

# ДАТА-КАТАЛОГ: ЛОЯЛЬНОСТЬ (LOYALTY)

| Таблица | Назначение | Основные поля |
|---------|------------|---------------|
| **loyalty_program_settings** | Настройки программы лояльности | shop_id (PK), bonuses_enabled, discounts_enabled, bonuses_order_share_reward, bonuses_expire_delay |
| **loyalty_levels** | Уровни лояльности | shop_id, code, name, threshold, order_share_as_bonus, discount_percentage |
| **loyalty_program_members** | Участники программы | shop_id, identifier, secret, pin, has_apple_wallet, has_google_wallet |
| **loyalty_bonus_transactions** | Бонусные транзакции | identifier, order_id, amount, aasm_state, event_source, expiration_date |
| **bonus_histories** | История движения бонусного счета | shop_id, client_id, code, total_balance, used, burned, rewarded, order_id, event |
| **bonus_transaction_logs** | Детальный лог бонусных операций | shop_id, client_id, order_id, event, source_type, source_id, description |
| **loyalty_promos** | Промо-акции лояльности | shop_id, name, aasm_state, conditions, reward_type, reward_rules |
| **loyalty_certificate_pools** | Пулы подарочных сертификатов | shop_id, code, name, nominal, expiration_days, min_order_value |
| **loyalty_certificates** | Подарочные сертификаты | shop_id, code, aasm_state, nominal, balance, owner_identifier |
| **loyalty_certificate_transactions** | Транзакции сертификатов | certificate_id, amount, event, order_uniqid |
| **loyalty_sticker_campaigns** | Кампании стикеров | shop_id, code, name |
| **loyalty_stickers** | Стикеры/баллы накопления | shop_id, identifier, aasm_state, issued_by_order_uniqid |
| **loyalty_bulk_rewards** | Массовые начисления бонусов | shop_id, name, audience_type, amount, expiration_type |
| **loyalty_wallets** | Настройки мобильных кошельков | shop_id, logo, background_color, apple_certificate, google_service_key |
| **loyalty_wallet_tokens** | Токены мобильных кошельков | identifier, ios_token |
| **loyalty_reports** | Отчеты по лояльности | shop_id, date, report |
| **client_loyalties** | Привязка клиента к программе | client_id, loyalty_id |
| **client_loyalty_levels** | Текущий уровень клиента | identifier, loyalty_level_id, expiration_date |
| **referral_programs** | Реферальные программы | shop_id, name, prefix, referral_reward_value, referrer_reward_value |
| **referral_program_partners** | Партнеры реферальных программ | identifier, code, referral_program_id |

---

# ДАТА-КАТАЛОГ: СЕГМЕНТЫ (SEGMENTS)

| Таблица | Назначение | Основные поля |
|---------|------------|---------------|
| **segments** | Сегменты аудитории | shop_id, name, segment_type, rules, auto_update, client_statistics |
| **segment_joins** | Связка клиентов с сегментами | segment_id, join_id |
| **rfms** | Настройки RFM-аналитики | shop_id (PK), count, months, monetary_min, monetary_max |
| **tags** | Теги для клиентов/сущностей | shop_id, name |

---

# ДАТА-КАТАЛОГ: ПОИСК (SEARCH)

| Таблица | Назначение | Основные поля |
|---------|------------|---------------|
| **search_settings** | Настройки поиска | shop_id (uniq), language, search_type, fuzziness, template |
| **search_queries** | Лог поисковых запросов | shop_id, client_id, query, date |
| **search_terms** | Словарь терминов поиска | shop_id, term, source |
| **search_boosts** | Повышение релевантности | shop_id, search_text, boost_type, boost_type_value, boost |
| **search_hard_boosts** | Жесткое закрепление в выдаче | shop_id, query, boost_type, boost_value, position |
| **search_query_redirects** | Редиректы поисковых запросов | shop_id, query, redirect_link, active |
| **no_result_queries** | Запросы без результатов | shop_id, query, query_count, synonym, date |
| **search_results** | Количество результатов по запросам | shop_id, query, total, date |
| **suggested_stop_words** | Предложенные стоп-слова | shop_id, keyword |
| **suggested_synonyms** | Предложенные синонимы | shop_id, query, synonym |
| **synonym_groups** | Группы синонимов | query, synonyms, category_ids |
| **wear_type_dictionaries** | Словарь типов одежды | type_name, word |
| **search_filter_usage** | Статистика использования фильтров | shop_id, filter_key, filter_value, value, date |
| **search_events** | Поисковые события | shop_id, did, event, query, input_query, segment, date |

---

# ДАТА-КАТАЛОГ: ИНТЕГРАЦИИ (INTEGRATIONS)

| Таблица | Назначение | Основные поля |
|---------|------------|---------------|
| **insales_shops** | Интеграция с InSales | shop_id, insales_shop, token, installed |
| **shopify_shops** | Интеграция с Shopify | shop_id, domain, token, api_key, api_secret |
| **cmses** | Справочник CMS | code, name |

---

# ДАТА-КАТАЛОГ: НАСТРОЙКИ МАГАЗИНА (SHOP SETTINGS)

| Таблица | Назначение | Основные поля |
|---------|------------|---------------|
| **shops** | Основная информация о магазине | uniqid, name, active, url, plan, balance, currency_id, time_zone, yml_settings, integration_flags |
| **mailings_settings** | Настройки рассылок | shop_id (PK), send_from, reply_to, telegram_token, chain_silent |
| **search_settings** | Настройки поиска | см. раздел ПОИСК |
| **web_push_subscriptions_settings** | Настройки web-push | shop_id, enabled, header, text, vapid_keys, certificate_settings |
| **sms_transports** | Настройки SMS-провайдеров | shop_id, provider, login, password, sender_name, enabled |
| **whatsapp_transports** | Настройки WhatsApp | shop_id, provider, host, login, password |
| **email_domains** | Домены отправителей email | shop_id, domain, dkim, spf, dmarc, reply_to |
| **shop_emails** | Email-адреса клиентов | см. раздел КЛИЕНТЫ |
| **shop_phones** | Телефоны магазина | shop_id, phone, phone_update_date, date |
| **shop_images** | Изображения магазина | shop_id, file, image_type |
| **shop_locations** | Локации/точки продаж | shop_id, external_id, name, parent_id, group |
| **shop_themes** | Темы оформления | shop_id, theme_id, theme_type, variables, compiled_css, is_custom |
| **styles** | Стили/шаблоны | shop_id, theme_id, category_listing_template |
| **currencies** | Справочник валют | code, symbol, exchange_rate, payable |
| **shop_metrics** | Метрики магазина | shop_id, date, orders, revenue, clients, offline_orders, channel_metrics |
| **shop_logs** | Логи действий в магазине | shop_id, who, product, event, customer_id |
| **shop_balance_histories** | История баланса | shop_id, message |
| **wizard_configurations** | Настройки онбординга | shop_id, industrials, triggers, completed, cdp, rfm, nps, product_recommendations |
| **deliverability_domains** | Доставляемость по почтовым доменам | shop_id, domain, event, value, date |
| **device_events** | События устройств на сайте | shop_id, did, sid, event, url, ip, stream, date |
| **shop_devices** | Характеристики устройств | shop_id, did, bot, device, browser, os, useragent, date |
| **utm** | UTM-метки визитов | shop_id, did, sid, param, value, date |

---

# ДАТА-КАТАЛОГ: БИЛЛИНГ (BILLING)

| Таблица | Назначение | Основные поля |
|---------|------------|---------------|
| **charges** | Списания со счета | shop_id, amount, description, charge_type, aasm_state |
| **invoices** | Счета на оплату | shop_id, customer_id, amount, aasm_state, payment_method |
| **subscription_plans** | Тарифные планы | shop_id, product, active, price |
| **currencies** | Валюты | см. раздел НАСТРОЙКИ |

---

# ДАТА-КАТАЛОГ: ТЕЛЕФОНИЯ (CALLS)

| Таблица | Назначение | Основные поля |
|---------|------------|---------------|
| **call_channels** | Каналы звонков | shop_id, name, key |
| **call_types** | Типы звонков | shop_id, name, key |
| **call_themes** | Темы звонков (иерархия) | shop_id, call_type, name, key, parent_id |
| **call_events** | События звонков | shop_id, call_channel, name, key |
| **client_calls** | Звонки клиентов | client_id, call_type, call_event, call_theme, comment |
| **client_call_entities** | --- | --- |

---

# ДАТА-КАТАЛОГ: NPS И ОБРАТНАЯ СВЯЗЬ (NPS)

| Таблица | Назначение | Основные поля |
|---------|------------|---------------|
| **nps_categories** | Категории NPS | shop_id, code, name, promoter_question, detractor_question |
| **nps_channels** | Каналы сбора NPS | shop_id, code, name |
| **nps_reviews** | NPS-оценки | client_id, order_id, nps_category_id, nps_channel_id, rate, comment |
| **reputations** | Отзывы | см. раздел ЗАКАЗЫ |
| **chat_reports** | Отчеты из чата | shop_id, email, phone, platform, code, data |

---

# ДАТА-КАТАЛОГ: УСТРОЙСТВА (DEVICES)

| Таблица | Назначение | Основные поля |
|---------|------------|---------------|
| **devices** | Устройства | code (PK), platform, user_agent, stream, ios_advertising_id |
| **device_clients** | Связь устройств с клиентами | code, client_id, shop_id |
| **mobile_push_tokens** | Push-токены мобильных устройств | client_id, token, platform, did |
| **web_push_tokens** | Push-токены браузеров | client_id, token, browser, did |

---

# ДАТА-КАТАЛОГ: УТИЛИТЫ (UTILITIES)

| Таблица | Назначение | Основные поля |
|---------|------------|---------------|
| **email_blocks** | Переиспользуемые блоки для писем | shop_id, code, name, body |
| **promo_code_lists** | Списки промокодов | shop_id, uid, name, sort_order |
| **promo_codes** | Промокоды | promo_code_list_id, code, client_id, source_type |
| **sent_promo_codes** | Отправленные промокоды | promo_code_list_id, code, client_id, is_used, order_uniqid |
| **one_time_passwords** | Одноразовые пароли (SMS) | shop_id, event, phone, code |
| **invalid_emails** | Невалидные email-адреса | email, reason |
| **unprocessed_emails** | Необработанные email | type, content |
| **entity_tags** | Универсальные теги | entity_type, entity_id, tag |
| **events** | Системные события | shop_id, name, additional_info, processed |
| **export_logs** | Логи экспорта данных | shop_id, export_type, state |
| **testers_groups** | Группы тестировщиков | shop_id, name, contacts_list |
| **product_parameters** | Параметры товаров | см. раздел ТОВАРЫ |
| **single_properties** | Одиночные свойства | code, value |
| **funnels** | Воронки продаж | shop_id, name, rules, settings |
| **custom_events** | Кастомные события лояльности | shop_id, key, name, rewardable, reward |
| **events_payloads** | Расширенные данные событий | shop_id, client_id, code, key, value_int, value_float, value_string, value_date |