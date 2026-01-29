# Таблица: also_viewed  
Синонимы: ---
Использование: для анализа рекомендаций
Описание: товары, которые смотрели клиенты при покупке
- **shop_id**: ID магазина (uint32)
- **client_id**: ID клиента (uint64)
- **items**: ID Товаров (Float32)
- **date**: дата (datetime64)


# Таблица: bulk_messages
Синонимы: массовые рассылки, письма, отправка, открытие
Использование: для анализа массовых рассылок, наилучшего времени отправки, рассчета конверсии отправки в открытие и т.д.
Описание: массовые рассылки. Делать анализ вместе с таблицей bulk_messages_hot объединяя их методом UNION
-   **shop_id** :          ID магазина                        (uint32)       
-  **bulk_campaign_id**:  ID массовой рассылки                (uint32)       
-  **client_id** :        ID клиента                          (uint64)       
-  **code** :             код письма                          (string)       
-   **event** : событие, действие над сообщением: Soft Bounce, Hard bounce - невозможность доставки, send - отправка,   (string)       
-  **channel** : канал, по которому делается рассылка         (string)       
-  **category** :         ---                                 (string)       
-  **platform** : тип устройства, с которого пришло событие   (string)       
-  **uid** :      -----------------------                     (string)       
-  **message_data**:      ---                                 (string)       
-  **stream**:источник события. Значения: web - сайт, ios - приложение на iOS, android - приложение на android, pos - кассы (string)       
-  **date**  :            дата создания записи                (datetime64)
-  **created_at** :       дата + время создания записи        (datetime64)
-  **location** :         ---                                 (string) 

# Таблица: bulk_messages_hot
Синонимы: массовые рассылки, письма, отправка, открытие
Использование: для анализа массовых рассылок, наилучшего времени отправки, рассчета конверсии отправки в открытие и т.д.
Описание: массовые рассылки. Делать анализ вместе с таблицей bulk_messages объединяя их методом UNION
-  **shop_id** :          ID магазина                        (uint32)       
-  **bulk_campaign_id**:  ID массовой рассылки                (uint32)       
-  **client_id** :        ID клиента                          (uint64)       
-  **code** :             код письма                          (string)       
-   **event** :            событие, действие над сообщением   (string)       
-  **channel** : канал, по которому делается рассылка         (string)       
-  **category** :         ---                                 (string)       
-  **platform** : тип устройства, с которого пришло событие   (string)       
-  **uid** :      ------------------------                    (string)       
-  **message_data**:      ---                                 (string)       
-  **stream**:источник события. Значения: web - сайт, ios - приложение на iOS, android - приложение на android, pos - кассы (string)       
-  **date**  :            дата создания записи                (datetime64)
-  **created_at** :       дата + время создания записи        (datetime64)
-  **location** :         ---                                 (string) 

# Таблица: chain_messages
Синонимы: триггерные цепочки, рассылки от триггерных цепочек
Использование: для анализа массовых рассылок, рассчета конверсии отправки в открытие и т.д.
Описание: рассылки сообщений от триггерных цепочек
-  **shop_id** :    ID магазина                 (uint32)       
-  **chain_id** :   ID триггерной цепочки       (uint32)       
-  **client_id** :    ID клиента                (uint64)       
-  **code** :         код                (string)       
-  **event** :  событие, действие клиента   (string)       
- **channel** :   канал, по которому делается рассылка клиенту при активации триггерной цепочки   (string)       
-  **category** :     ---                                 (string)       
- **rule_id** :      ---                                   (string)       
-   **platform** :  тип устройства, с которого пришло событие    (string)       
-  **uid** :      email клиента                                  (string)       
-  **message_data**:  ---                                         (string)       
- **stream**:источник события. Значения: web - сайт, ios - приложение на iOS, android - приложение на android, pos - кассы (string)       
- **date** :          дата создания записи                   (datetime64)
-  **created_at**:    дата + время создания записи           (datetime64)
- **location** :     ---                                         (string) 

# Таблица: events
Синонимы: события, действия клиента на сайте, поисковая строка
Использование: для рассчета конверсий событий, конверсий использования поисковой строки, длительность сессий
Описание: события - действия клиента на сайте интернет-магазинов
-  **shop_id** :   ID магазина                        (uint32)       
-  **client_id** :  ID клиента                        (uint64)       
-   **event** : событие - действия клиента на сайте  (string)       
-   **code**:          код                             (string)       
-   **did** :         ID устройства, Device id         (string)       
-   **sid** :   ID интернет-сессии      (string)       
-   **category**: показывает с чем взаимодейсвует клиент. Если Item-товар, search-строка поиска  (string)       
-   **label**: ID товара                                                                         (string)       
-  **value** :      цена товара                                                                  (float64)      
-   **recommended_by**: откуда клиент пришел на сайт. С рассылки, триггерной цепочки и т.д.       (string)       
-  **recommended_code** : код, по которому можно проследить путь клиента                          (string)       
-  **segment** :          ---                                                                      (string)       
-  **brand**:          бренд товара                                                                (string)       
-  **referer** :          -------------------------------                                          (string)       
-  **created_at**:       дата + время создания записи                                            (datetime64)
-  **date**  :            дата создания записи                                                   (datetime64)
-  **sign** :          состояние                                                                   (int8)        
-  **stream** : источник события. Значения: web - сайт, ios - приложение на iOS, android - приложение на android, pos - кассы (string)       
-  **categories**:  ---                                                                             (string)   

# Таблица: order_items
Синонимы: order, покупка, транзакция, purchases
Использование: для анализа продаж, статистики заказов, топ товаров
Описание: Покупки, суммы заказов, заказы товаров, совершенные клиентами на сайте магазина
-  **did** :        ID устройства, Device id                                           (string)       
-   **client_id**:    ID клиента                                                       (uint64)       
-  **shop_id** :          ID магазина                                                  (uint32)    
-   **order_id** :             ID покупки                                               (uint64)       
-   **item_uniqid**:          ID товара                                                 (string)       
-  **amount** :               количество товара в покупке                                            (uint32)       
-   **price** :                цена товара при покупке                                               (float32)      
-  **recommended_by**:с какого источника перешел клиент на карточку товара: instant_search-быстрый поиск, dinamic-рекомендации, full_search-полный поиск,chain_message-триггерная цепочка (string)      
-   **recommended_code** :код, по которому можно отследить цепочку действий клиента, для search - поисковый запрос    (string)       
-   **recommended_additional_code** : ---                                                                                                (string)       
-  **recommended_channel**: канал, откуда перешел клиент на карточку товара. Значения 'email', 'web_push', 'mobile_push', 'sms', 'telegram'                  (string)       
-  **recommended_id** :      ID перехода на сайт                                                   (UInt64)       
-  **segment** :             ---                                   (string)       
-  **brand** :           бренд                                     (string)       
-  **offline**: показывает, каким способом была совершена покупка. Если через интернет-магазин = 0; если через обычный offline физический магазин = 1                            (UInt8)        
-  **categories** :  ---                                                                              (object)       
- **stream**  : источник события. Значения: web - сайт, ios - приложение на iOS, android - приложение на android, pos - кассы  (string)       
-  **status** :  статус заказа                                                      (string)       
-  **original_price** :  ---                                                                            (float64)      
-  **discount_product** :   ---                                                                          (float64)      
-  **discount_coupon**  :   ---                                                                             (float64)      
-  **discount_bonuses** :  ---                                                                             (float64)      
-  **delivery_company** :  компания по доставке                                                              (string)       
-  **barcode** :   ---                                                                                       (string)       
-  **line_id** :   -------------------                                                                     (string)       
- **cancel_reason**:   ---                                                                               (string)       
- **created_at** :     дата + время создания записи                                                        (datetime64)
- **date** :           дата создания записи                                                                (datetime64)
-  **version** :      ---                                                                                  (datetime64)
-  **sid**   :      ID сессии, вход на сайт                                                                (string) 

# Таблица: popup_events
Синонимы: 'popup', 'попап', 'всплывающее окно'
Использование: для анализа конверсии, выручки от popup
Описание: события попапов. Попап - всплывающее сообщение для клиента на сайте, напоминающее о чем либо, предлагающее скидку и т.д.
-  **client_id**:   ID клиента               (uint64)       
-  **did** :       ID устройства, Device id   (string)       
-  **sid** :       ID сессии, вход на сайт     (string)       
-  **shop_id** :   ID магазина                  (uint32)       
-   **popup_id**:   ID попапа                    (uint32)       
-  **event** :      событие, действие             (string)       
-   **channel** : ----------------------------------     (string)       
-   **created_at**:  дата + время создания записи                             (datetime64)
-  **date**  :       дата создания записи                                     (datetime64)

# Таблица: search_events
Описание: История взаимодействий с поисковой строкой
-  **shop_id** :   ID магазина          (uint32)       
-  **did** : ID устройства, Device id    (string)       
-  **event** :   событие, действие        (string)  
-  **input_query**: поисковый запрос, введенный в поисковую строку пользователем     (string)      
-  **query** : запрос предложенный сайтом исходя из поля input_query                      (string)             
-   **segment**:     -----------------------                  (string)       
-  **date**:       дата создания записи                    (datetime64)
-   **created_at**:  дата + время создания записи          (datetime64)

# Таблица: story_events
Описание: события сторис, story, stories
-  **shop_id**:  ID магазина      (uint32)       
-  **story_id** :  ID story        (uint32)      
-   **client_id** : ID клиента      (uint64)       
-  **event** :  действие со story, сторис   (string)       
-  **story_slide_id**:  ID слайда story       (string)       
-   **sid** :  ID сессии, вход на сайт      (string)       
-   **stream** :источник события. Значения: web - сайт, ios - приложение на iOS, android - приложение на android, pos - кассы (string)       
-  **code** : код блока story                                          (string)       
-   **date** : дата создания записи                          (datetime64)
-  **created_at**: дата + время создания записи              (datetime64)
