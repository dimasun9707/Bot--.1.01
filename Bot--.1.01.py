import asyncio
from typing import Tuple
import pandas as pd
from datetime import datetime
import MetaTrader5 as mt5
import pytz
import time
# import pyEX as p
import numpy as np


async def Send_stop(symbol, lot, ok, spread, jump, tf, ts):
    global buy_positions, sell_positions
    global buy_orders_price, sell_orders_price
    global buy_orders_ticket, sell_orders_ticket
    global b, a
    symbol = symbol
    lot = lot
    ok = ok
    spread = spread
    jump = jump
    tf = tf
    ts = ts
    while True:
        print('вход', symbol)

        def connect():
            # установим подключение к терминалу MetaTrader 5
            if not mt5.initialize():
                print("initialize() failed, error code =", mt5.last_error())
                quit()

            # подготовим структуру запроса для покупки
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                print(symbol, "not found, can not call order_check()")
                mt5.shutdown()
                quit()

            # если символ недоступен в MarketWatch, добавим его
            if not symbol_info.visible:
                print(symbol, "is not visible, trying to switch on")
                if not mt5.symbol_select(symbol, True):
                    print("symbol_select({}}) failed, exit", symbol)
                    mt5.shutdown()
                    quit()
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info != None:
                trade_tick_value = symbol_info.trade_tick_value  # if symbol is XAG *10
                return trade_tick_value, symbol_info
            quit()
            mt5.shutdown()

        trade_tick_value, symbol_info = connect()

        connect()
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, 100)
        rates_frame = pd.DataFrame(rates)

        def will_frac_roll(df: pd.DataFrame, period: int = 2) -> Tuple[pd.Series, pd.Series]:
            """Indicate bearish and bullish fractal patterns using rolling windows.

                :param df: OHLC data
                :param period: number of lower (or higher) points on each side of a high (or low)
                :return: tuple of boolean Series (bearish, bullish) where True marks a fractal pattern
                """
            window = 2 * period + 1  # default 5
            bears = df['high'].rolling(window, center=True).apply(lambda x: x[period] == max(x), raw=True)
            bulls = df['low'].rolling(window, center=True).apply(lambda x: x[period] == min(x), raw=True)

            return bears, bulls

        c = will_frac_roll(rates_frame)

        def get_fractal():
            bears = c[0]
            bulls = c[1]
            bears = bears[bears > 0]  # Вывод медвежьих значений, где значение индекса больше 0.
            bulls = bulls[bulls > 0]  # Вывод медвежьих значений, где значение индекса больше 0.
            end_bears = bears.index[-1]  # Берем индекс последнего бычьего фрактала.
            end_bulls = bulls.index[-1]  # Берем индекс последнего медвежьего фрактала.
            hf = rates_frame.iloc[end_bears]  # Получаем данные из датафрейма по индексу бычьего фрактала.
            lf = rates_frame.iloc[end_bulls]  # Получаем данные из датафрейма по индексу медвежьего фрактала.
            hf = (hf['high'] + spread)  # high fractal + spread.    Получаем цену high
            lf = (lf['low'])  # low fractal.                      Получаем цену low
            return hf, lf

        hf, lf = get_fractal()

        # выведем информацию о действующих отложенных ордерах на символе EURUSD\
        connect()

        def get_orders():
            orders = mt5.orders_get(symbol=symbol)
            if orders is None:
                print("No orders on {}, error code={}".format(symbol, mt5.last_error()))
            elif len(orders) > 0:
                orders_df = pd.DataFrame(list(orders), columns=orders[0]._asdict().keys())
                orders_df.drop(
                    ['time_setup', 'time_setup_msc', 'time_done', 'time_done_msc',
                     'time_expiration', 'type_time', 'type_filling', 'state',
                     'magic', 'position_id', 'position_by_id', 'reason', 'volume_initial',
                     'volume_current',
                     'symbol', 'external_id'],
                    axis=1, inplace=True)
                return orders_df

        orders_df = get_orders()
        print(orders_df)

        if orders_df is not None:
            if orders_df.empty is False:
                sell_orders = orders_df[orders_df['comment'] == "SELL {}".format(symbol)]
                if sell_orders.empty:
                    sell_orders_price = None
                    sell_orders_ticket = None
                else:
                    sell_orders_price = float(sell_orders['price_open'].tail(1))
                    sell_orders_ticket = list(sell_orders['ticket'].tail(1))
            else:
                sell_orders_price = None
                sell_orders_ticket = None
        else:
            sell_orders_price = None
            sell_orders_ticket = None

        # print(f'Покупка', buy_orders_price)

        if orders_df is not None:
            if orders_df.empty is False:
                buy_orders = orders_df[orders_df['comment'] == "BUY {}".format(symbol)]
                if buy_orders.empty:
                    buy_orders_price = None
                    buy_orders_ticket = None
                else:
                    buy_orders_price = float(buy_orders['price_open'].tail(1))
                    buy_orders_ticket = list(buy_orders['ticket'].tail(1))
                    # print('132', buy_orders_price)
            else:
                buy_orders_price = None
                buy_orders_ticket = None
                # print('136', buy_orders_price)
        else:
            buy_orders_price = None
            buy_orders_ticket = None
            # print('140', buy_orders_price)

        connect()

        def get_positions():
            # global p_df
            positions_total = mt5.positions_total()
            if positions_total is not None:
                if positions_total > 0:
                    positions = (mt5.positions_get(symbol=symbol))
                    if len(positions) > 0:
                        p_df = pd.DataFrame(list(positions), columns=positions[0]._asdict().keys())
                        p_df.drop(
                            ['time', 'time_update', 'time_msc',
                             'time_update_msc', 'type', 'magic', 'identifier',
                             'reason', 'reason', 'external_id'],
                            axis=1, inplace=True)
                        return p_df
                    else:
                        p_df = None

            else:
                print("Positions not found")

        p_df = get_positions()
        print('170', p_df)

        def get_sp_op():
            if p_df is not None:
                if p_df.empty is False:
                    sell_positions = p_df[(p_df["comment"] == "SELL {}".format(symbol))]
                    sp_op = sell_positions.price_open
                    print('176', sp_op)
                    return sp_op  # sell_positions,

            else:
                sp_op = None
                # sell_positions = None
                return sp_op  # sell_positions,

        # sell_positions, \
        sp_op = get_sp_op()

        def get_bp_op():
            if p_df is not None:
                if p_df.empty is False:
                    buy_positions = p_df[(p_df["comment"] == "BUY {}".format(symbol))]
                    bp_op = buy_positions.price_open
                    print('189', bp_op)
                    return buy_positions, bp_op
            else:
                bp_op = None
                buy_positions = None
                return buy_positions, bp_op

        buy_positions, bp_op = get_bp_op()
        # print(type(bp_op))

        # Блок баланса
        connect()

        # def get_balance():
        #     account_info = mt5.account_info()
        #     if account_info != None:
        #         account_info_dict = mt5.account_info()._asdict()
        #         balance_df = pd.DataFrame(list(account_info_dict.items()), columns=['property', 'value'])
        #         balance_df = (balance_df.iloc[10][1])
        #         return balance_df
        #     else:
        #         print("failed to connect to trade account 25115284 with password=gqz0343lbdm, error code =",
        #               mt5.last_error())
        #
        #
        # balance_df = get_balance()

        share = 30  # количество частей
        price = mt5.symbol_info_tick(symbol).ask
        deviation = 0

        # def get_risk():
        #     risk = (balance_df / share // trade_tick_value)
        #     return risk  # в пипсах
        #
        #
        # risk = get_risk()

        # def get_sum_risk():
        #     sum_risk = (balance_df // share)
        #     return sum_risk

        # sum_risk = get_sum_risk()

        # def get_lot():
        #     lot = sum_risk // (trade_tick_value * risk)
        #     return lot

        # lot = get_lot()

        # Блок продажи.
        connect()

        def send_sell_stop():
            connect()
            request = {
                "action": mt5.TRADE_ACTION_PENDING,
                "symbol": symbol,
                "volume": lot,
                "type": mt5.ORDER_TYPE_SELL_STOP,
                "price": hf,
                "sl": hf + jump,  # price - 100 * point,
                "tp": lf,  # jump
                "deviation": deviation,
                "magic": 234000,
                "comment": "SELL {}".format(symbol),
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_FOK,
            }
            # отправим торговый запрос
            result = mt5.order_send(request)
            # проверим результат выполнения
            print(
                "1. send_sell_stop(): by {} {} lots at {} with deviation={} points".format(symbol, lot, hf, deviation))
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                print("2. send_sell_stop failed Продажа, retcode={}".format(result.retcode))
                # запросим результат в виде словаря и выведем поэлементно
                result_dict = result._asdict()
                for field in result_dict.keys():
                    print("   {}={}".format(field, result_dict[field]))
                    # если это структура торгового запроса, то выведем её тоже поэлементно
                    if field == "request":
                        traderequest_dict = result_dict[field]._asdict()
                        for tradereq_filed in traderequest_dict:
                            print(
                                "       traderequest: {}={}".format(tradereq_filed, traderequest_dict[tradereq_filed]))
                print("shutdown() and quit")
                mt5.shutdown()
                quit()

        def send_sell_limit():
            connect()
            request = {
                "action": mt5.TRADE_ACTION_PENDING,
                "symbol": symbol,
                "volume": lot,
                "type": mt5.ORDER_TYPE_SELL_LIMIT,
                "price": hf,
                "sl": hf + jump,  # price - 100 * point,
                "tp": lf,  # jump
                "deviation": deviation,
                "magic": 234000,
                "comment": "SELL {}".format(symbol),
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_FOK,
            }
            # отправим торговый запрос
            result = mt5.order_send(request)
            # проверим результат выполнения
            print(
                "1. send_sell_limit(): by {} {} lots at {} with deviation={} points".format(symbol, lot, hf, deviation))
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                print("2. send_sell_limit failed Продажа, retcode={}".format(result.retcode))
                # запросим результат в виде словаря и выведем поэлементно
                result_dict = result._asdict()
                for field in result_dict.keys():
                    print("   {}={}".format(field, result_dict[field]))
                    # если это структура торгового запроса, то выведем её тоже поэлементно
                    if field == "request":
                        traderequest_dict = result_dict[field]._asdict()
                        for tradereq_filed in traderequest_dict:
                            print(
                                "       traderequest: {}={}".format(tradereq_filed, traderequest_dict[tradereq_filed]))
                print("shutdown() and quit")
                mt5.shutdown()
                quit()

        # Блок покупки
        #
        # Отложенная покупка
        connect()

        def send_buy_stop():
            request = {
                "action": mt5.TRADE_ACTION_PENDING,
                "symbol": symbol,
                "volume": lot,
                "type": mt5.ORDER_TYPE_BUY_STOP,
                "price": lf,
                "sl": lf - jump,  # price - 100 * point,
                "tp": hf,
                "deviation": 0,
                "magic": 234000,
                "comment": "BUY {}".format(symbol),
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_FOK,
            }
            # отправим торговый запрос
            result = mt5.order_send(request)
            # проверим результат выполнения
            print("1. send_buy_stop(): by {} {} lots at {} with deviation={} points".format(symbol, lot, lf, deviation))
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                print("2. send_buy_stop failed Покупка, retcode={}".format(result.retcode))
                # запросим результат в виде словаря и выведем поэлементно
                result_dict = result._asdict()
                for field in result_dict.keys():
                    print("   {}={}".format(field, result_dict[field]))
                    # print(f' retcode = ', result_dict.keys(retcode))
                    # if result_dict.keys(retcode) == 10015:

                    # если это структура торгового запроса, то выведем её тоже поэлементно
                    if field == "request":
                        traderequest_dict = result_dict[field]._asdict()
                        for tradereq_filed in traderequest_dict:
                            print("       traderequest: {}={}".format(tradereq_filed,
                                                                      traderequest_dict[tradereq_filed]))
                print("shutdown() and quit")
                mt5.shutdown()
                quit()

        def send_buy_limit():
            request = {
                "action": mt5.TRADE_ACTION_PENDING,
                "symbol": symbol,
                "volume": lot,
                "type": mt5.ORDER_TYPE_BUY_LIMIT,
                "price": lf,
                "sl": lf - jump,  # price - 100 * point,
                "tp": hf,
                "deviation": 0,
                "magic": 234000,
                "comment": "BUY {}".format(symbol),
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_FOK,
            }
            # отправим торговый запрос
            result = mt5.order_send(request)
            # проверим результат выполнения
            print(
                "1. send_buy_limit(): by {} {} lots at {} with deviation={} points".format(symbol, lot, lf, deviation))
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                print("2. send_buy_limit failed Покупка, retcode={}".format(result.retcode))
                # запросим результат в виде словаря и выведем поэлементно
                result_dict = result._asdict()
                for field in result_dict.keys():
                    print("   {}={}".format(field, result_dict[field]))
                    # print(f' retcode = ', result_dict.keys(retcode))
                    # if result_dict.keys(retcode) == 10015:

                    # если это структура торгового запроса, то выведем её тоже поэлементно
                    if field == "request":
                        traderequest_dict = result_dict[field]._asdict()
                        for tradereq_filed in traderequest_dict:
                            print("       traderequest: {}={}".format(tradereq_filed,
                                                                      traderequest_dict[tradereq_filed]))
                print("shutdown() and quit")
                mt5.shutdown()
                quit()

        # def send_buy_stop_limit():
        #     request = {
        #         "action": mt5.TRADE_ACTION_PENDING,
        #         "symbol": symbol,
        #         "volume": lot,
        #         "type": mt5.ORDER_TYPE_BUY_LIMIT,
        #         "price": lf,
        #         "sl": lf + jump,  # price - 100 * point,
        #         "tp": hf,
        #         "deviation": 0,
        #         "magic": 234000,
        #         "comment": "BUY {}".format(symbol),
        #         "type_time": mt5.ORDER_TIME_GTC,
        #         "type_filling": mt5.ORDER_FILLING_FOK,
        #     }
        #     # отправим торговый запрос
        #     result = mt5.order_send(request)
        #     # проверим результат выполнения
        #     print("1. send_buy_stop(): by {} {} lots at {} with deviation={} points".format(symbol, lot, hf, deviation))
        #     if result.retcode != mt5.TRADE_RETCODE_DONE:
        #         print("2. send_buy_stop failed Покупка, retcode={}".format(result.retcode))
        #         # запросим результат в виде словаря и выведем поэлементно
        #         result_dict = result._asdict()
        #         for field in result_dict.keys():
        #             print("   {}={}".format(field, result_dict[field]))
        #             # print(f' retcode = ', result_dict.keys(retcode))
        #             # if result_dict.keys(retcode) == 10015:
        #
        #             # если это структура торгового запроса, то выведем её тоже поэлементно
        #             if field == "request":
        #                 traderequest_dict = result_dict[field]._asdict()
        #                 for tradereq_filed in traderequest_dict:
        #                     print("       traderequest: {}={}".format(tradereq_filed,
        #                                                               traderequest_dict[tradereq_filed]))
        #         print("shutdown() and quit")
        #         mt5.shutdown()
        #         quit()

        # def send_sell_stop_limit():
        #     request = {
        #         "action": mt5.TRADE_ACTION_PENDING,
        #         "symbol": symbol,
        #         "volume": lot,
        #         "type": mt5.ORDER_TYPE_SELL_LIMIT,
        #         "price": hf,
        #         "sl": hf + jump,  # price - 100 * point,
        #         "tp": lf,
        #         "deviation": 0,
        #         "magic": 234000,
        #         "comment": "SELL {}".format(symbol),
        #         "type_time": mt5.ORDER_TIME_GTC,
        #         "type_filling": mt5.ORDER_FILLING_FOK,
        #     }
        #     # отправим торговый запрос
        #     result = mt5.order_send(request)
        #     # проверим результат выполнения
        #     print("1. send_buy_stop(): by {} {} lots at {} with deviation={} points".format(symbol, lot, hf, deviation))
        #     if result.retcode != mt5.TRADE_RETCODE_DONE:
        #         print("2. send_buy_stop failed Покупка, retcode={}".format(result.retcode))
        #         # запросим результат в виде словаря и выведем поэлементно
        #         result_dict = result._asdict()
        #         for field in result_dict.keys():
        #             print("   {}={}".format(field, result_dict[field]))
        #             # print(f' retcode = ', result_dict.keys(retcode))
        #             # if result_dict.keys(retcode) == 10015:
        #
        #             # если это структура торгового запроса, то выведем её тоже поэлементно
        #             if field == "request":
        #                 traderequest_dict = result_dict[field]._asdict()
        #                 for tradereq_filed in traderequest_dict:
        #                     print("       traderequest: {}={}".format(tradereq_filed,
        #                                                               traderequest_dict[tradereq_filed]))
        #         print("shutdown() and quit")
        #         mt5.shutdown()
        #         quit()

        connect()

        # def get_ma():
        #     df = rates_frame
        #     df = df[['close']]
        #     df.reset_index(level=0, inplace=True)
        #     df.columns = ['ds', 'y']
        #     rolling_mean = df.y.rolling(window=35).mean()
        #     rolling_mean = round(rolling_mean.tail(1), 3)
        #
        #     return rolling_mean
        #
        #
        # rolling_mean = get_ma()

        def orders_removed(buy_orders_ticket):
            request = {
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": buy_orders_ticket,
            }
            # отправим торговый запрос
            result_mod = mt5.order_send(request)
            # проверим результат выполнения
            print("1. orders_removed(): by {} {} lots at {} with deviation={} points".format(symbol, lot, price,
                                                                                             deviation))
            if result_mod.retcode != mt5.TRADE_RETCODE_DONE:
                print("2. orders_removed failed, retcode={}".format(result_mod.retcode))
                # запросим результат в виде словаря и выведем поэлементно
                result_dict = result_mod._asdict()
                for field in result_dict.keys():
                    print("   {}={}".format(field, result_dict[field]))
                    # если это структура торгового запроса, то выведем её тоже поэлементно
                    if field == "request":
                        traderequest_dict = result_dict[field]._asdict()
                        for tradereq_filed in traderequest_dict:
                            print("       traderequest: {}={}".format(tradereq_filed,
                                                                      traderequest_dict[tradereq_filed]))
                return result_mod
            print("shutdown() and quit")
            mt5.shutdown()
            quit()

        # def buy_modification(ticket, tp):
        #     request = {
        #         "action": mt5.TRADE_ACTION_SLTP,
        #         "symbol": symbol,
        #         "sl": lf,
        #         "tp": tp,
        #         "position": ticket,
        #     }
        #     # отправим торговый запрос
        #     result_mod = mt5.order_send(request)
        #     # проверим результат выполнения
        #     print("1. buy_modification(): by {} {} lots at {} with deviation={} points".format(symbol, lot, price, deviation))
        #     if result_mod.retcode != mt5.TRADE_RETCODE_DONE:
        #         print("2. buy_modification failed, retcode={}".format(result_mod.retcode))
        #         # запросим результат в виде словаря и выведем поэлементно
        #         result_dict = result_mod._asdict()
        #         for field in result_dict.keys():
        #             print("   {}={}".format(field, result_dict[field]))
        #             # если это структура торгового запроса, то выведем её тоже поэлементно
        #             if field == "request":
        #                 traderequest_dict = result_dict[field]._asdict()
        #                 for tradereq_filed in traderequest_dict:
        #                     print("       traderequest: {}={}".format(tradereq_filed,
        #                                                               traderequest_dict[tradereq_filed]))
        #             return result_mod
        #         print("shutdown() and quit")
        #         mt5.shutdown()
        #         quit()
        #
        #
        # def sell_modification(ticket, tp):
        #     print(symbol, hf, tp, ticket)
        #     request = {
        #         "action": mt5.TRADE_ACTION_SLTP,
        #         "symbol": symbol,
        #         "sl": hf,  # price - 100 * point,
        #         "tp": tp,
        #         "position": ticket,
        #     }
        #     # отправим торговый запрос
        #     result_mod = mt5.order_send(request)
        #     # проверим результат выполнения
        #     print("1. sell_modification(): by {} {} lots at {} with deviation={} points".format(symbol, lot, price, deviation))
        #     if result_mod.retcode != mt5.TRADE_RETCODE_DONE:
        #         print("2. sell_modification failed, retcode={}".format(result_mod.retcode))
        #         # запросим результат в виде словаря и выведем поэлементно
        #         result_dict = result_mod._asdict()
        #         for field in result_dict.keys():
        #             print("   {}={}".format(field, result_dict[field]))
        #             # если это структура торгового запроса, то выведем её тоже поэлементно
        #             if field == "request":
        #                 traderequest_dict = result_dict[field]._asdict()
        #                 for tradereq_filed in traderequest_dict:
        #                     print("       traderequest: {}={}".format(tradereq_filed,
        #                                                               traderequest_dict[tradereq_filed]))
        #             return result_mod
        #         print("shutdown() and quit")
        #         mt5.shutdown()
        #         quit()

        # sp_op.tolist(sp_op)
        # print('435', sp_op)
        # print('436', type(sp_op))
        def sp_op_lf(sp_op):
            if sp_op is not None:
                if sp_op.empty is False:
                    sp_op = list(sp_op)
                    sp_op.append(lf)
                    sp_op.sort()
                    a = sp_op.index(lf)
                    return a, sp_op

        if sp_op is not None:
            if sp_op.empty is False:
                a, sp_op = sp_op_lf(sp_op)
            else:
                a = None
                sp_op = None

        # print('447', sp_op)
        # print('448', type(sp_op))
        #
        #
        # print('449', bp_op)
        def bp_op_hf(bp_op):
            if bp_op is not None:
                if bp_op.empty is False:
                    bp_op = list(bp_op)
                    bp_op.append(hf)
                    bp_op.sort()
                    b = bp_op.index(hf)
                    # print('477', bp_op)
                    return b, bp_op

        if bp_op is not None:
            if bp_op.empty is False:
                b, bp_op = bp_op_hf(bp_op)
            else:
                b = None
                bp_op = None

        if price > hf:
            if sell_orders_price is None:
                if sp_op is not None:
                    # if sp_op.empty is False:
                    if a == 0:  # maybe match case?
                        i = sp_op[a + 1]
                        if (i - ok) > lf:  # or lf > (i + ok):
                            send_sell_stop()
                        else:
                            pass
                    else:
                        i = sp_op[a - 1]
                        if lf > (i + ok):
                            send_sell_stop()
                # else:
                #     try:
                #         send_sell_stop()
                #     except:
                #         pass
                else:
                    try:
                        send_sell_stop()
                    except:
                        pass
            elif (sell_orders_price - ok) > lf or lf > (sell_orders_price + ok):
                if sp_op is not None:
                    # if sp_op.empty is False:
                    for i in sp_op:
                        if (i - ok) > lf or lf > (i + ok):
                            try:
                                send_sell_stop()
                                orders_removed(sell_orders_ticket[0])

                            except:
                                pass
                # else:
                #     try:
                #         send_sell_stop()
                #         orders_removed(sell_orders_ticket[0])
                #
                #     except:
                #         pass
                else:
                    try:
                        send_sell_stop()
                        orders_removed(sell_orders_ticket[0])

                    except:
                        pass
        elif price < hf:
            if sell_orders_price is None:
                if sp_op is not None:
                    # if sp_op.empty is False:
                    if a == 0:  # maybe match case?
                        i = sp_op[a + 1]
                        if (i - ok) > lf:  # or lf > (i + ok):
                            send_sell_limit()
                        else:
                            pass
                    else:
                        i = sp_op[a - 1]
                        if lf > (i + ok):
                            send_sell_limit()
                # else:
                #     try:
                #         send_sell_stop()
                #     except:
                #         pass
                else:
                    try:
                        send_sell_limit()
                    except:
                        pass
            elif (sell_orders_price - ok) > lf or lf > (sell_orders_price + ok):
                if sp_op is not None:
                    pass
                    # if sp_op.empty is False:
                    #     for i in sp_op:
                    #         if (i - ok) > lf or lf > (i + ok):
                    #             try:
                    #                 orders_removed(sell_orders_ticket[0])
                    #
                    #             except:
                    #                 pass
                    # else:
                    #     try:
                    #         send_sell_stop()
                    #         orders_removed(sell_orders_ticket[0])
                    #
                    #     except:
                    #         pass
                else:
                    try:
                        send_sell_limit()
                        orders_removed(sell_orders_ticket[0])

                    except:
                        pass

        if price < lf:
            if buy_orders_price is None:
                if bp_op is not None:
                    # if bp_op.empty is False:
                    if b == 0:  # maybe match case?
                        i = bp_op[b + 1]
                        if (i - ok) > hf:  # or lf > (i + ok):
                            send_buy_stop()
                    else:
                        i = bp_op[b - 1]
                        if hf > (i + ok):
                            send_buy_stop()
                # else:
                #     try:
                #         send_buy_stop()
                #     except:
                #         pass
                else:
                    try:
                        send_buy_stop()
                    except:
                        pass
            elif (buy_orders_price - ok) > hf or hf > (buy_orders_price + ok):
                if bp_op is not None:
                    # if bp_op.empty is False:
                    for i in bp_op:
                        if (i - ok) > hf or hf > (i + ok):
                            try:
                                send_buy_stop()
                                orders_removed(buy_orders_ticket[0])
                            except:
                                pass
                # else:
                #     try:
                #         send_buy_stop()
                #         orders_removed(buy_orders_ticket[0])
                #     except:
                #         pass
                else:
                    try:
                        send_buy_stop()
                        orders_removed(buy_orders_ticket[0])
                    except:
                        pass
        elif price > lf:
            if buy_orders_price is None:
                if bp_op is not None:
                    # if bp_op. is False:
                    if b == 0:  # maybe match case?
                        i = bp_op[b + 1]
                        if (i - ok) > hf:  # or lf > (i + ok):
                            send_buy_limit()
                    else:
                        i = bp_op[b - 1]
                        if hf > (i + ok):
                            send_buy_limit()
                # else:
                #     try:
                #         send_buy_stop()
                #     except:
                #         pass
                else:
                    try:
                        send_buy_limit()
                    except:
                        pass
            elif (buy_orders_price - ok) > hf or hf > (buy_orders_price + ok):
                if bp_op is not None:
                    pass
                    # if bp_op.empty is False:
                    #     for i in bp_op:
                    #         if (i - ok) > hf or hf > (i + ok):
                    #             try:
                    #                 orders_removed(buy_orders_ticket[0])
                    #             except:
                    #                 pass
                    # else:
                    #     try:
                    #         send_buy_stop()
                    #         orders_removed(buy_orders_ticket[0])
                    #     except:
                    #         pass
                else:
                    try:
                        send_buy_limit()
                        orders_removed(buy_orders_ticket[0])
                    except:
                        pass

        # if buy_positions is not None:
        #     for row in buy_positions.itertuples():
        #         if lf != row.sl:
        #             ticket = row.ticket
        #             tp = row.tp
        #             buy_modification(ticket, tp)
        #
        #
        #
        #
        # if sell_positions is not None:
        #     for row in sell_positions.itertuples():
        #         if hf != row.sl:
        #             ticket = row.ticket
        #             tp = row.tp
        #             sell_modification(ticket, tp)

        print('Выход', symbol)
        print(datetime.now())
        await asyncio.sleep(delay=ts)


async def main():
    main_loop.create_task(
        Send_stop(symbol="XAGUSD", lot=0.01, ok=0.100, spread=0.025, jump=0.700, tf=mt5.TIMEFRAME_H1, ts=3600))
    main_loop.create_task(Send_stop(symbol="XAUUSD", lot=0.01, ok=3, spread=0.2, jump=20.00, tf=mt5.TIMEFRAME_H1,
                                    ts=14400))
    main_loop.create_task(
        Send_stop(symbol="AUDJPY", lot=0.01, ok=0.160, spread=0.015, jump=1.800, tf=mt5.TIMEFRAME_H1, ts=14400))
    # # # main_loop.create_task(Wti())
    main_loop.create_task(
        Send_stop(symbol="EURUSD", lot=0.01, ok=0.00160, spread=0.00003, jump=0.01280, tf=mt5.TIMEFRAME_H1,
                  ts=14400))
    main_loop.create_task(
        Send_stop(symbol="EURJPY", lot=0.01, ok=0.160, spread=0.06, jump=4, tf=mt5.TIMEFRAME_H1, ts=14400))
    main_loop.create_task(
        Send_stop(symbol="USDJPY", lot=0.01, ok=0.160, spread=0.06, jump=3.800, tf=mt5.TIMEFRAME_H1, ts=14400))


main_loop = asyncio.get_event_loop()
main_loop.run_until_complete(main())
# asyncio.ensure_future(main())
main_loop.run_forever()
