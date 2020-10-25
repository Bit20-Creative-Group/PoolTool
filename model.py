from pubsub import pub
import yaml
import re
import sys

from bitshares import BitShares
from bitshares.amount import Amount
from bitshares.asset import Asset
from bitshares.market import Market
from bitshares.price import Price

class Model:
    def __init__(self):
        self.get_settings()
        self.bitshares = BitShares(node='wss://btsfullnode.bangzi.info/ws')
        self.invert = False
        self.pool_id_or_sym = None

    def get_settings(self):
        with open('settings.yml') as file:
            self.settings =  yaml.safe_load(file)

    def quit_program(self):
        sys.exit(0)

    def update_prices(self, data):
        data['assets'] = re.sub('\(|\,|\'|\)', '', data['assets'])
        data['assets'] = data['assets'].split(' ')
        if data['selected_asset'] == 0:
            selected_asset = data['assets'][0]
            unselected_asset = data['assets'][1]
        else:
            selected_asset = data['assets'][1]
            unselected_asset = data['assets'][0]
        pool_cost_track = {'invariant': data['invariant']}
        if data['buy_or_sell'] == 'buy':
            if selected_asset == data['assets'][0]:
                # creates local variable for balance x
                reference_x = self.amount_x.amount
                # gets difference of what user wants vs pool
                difference_of_x = reference_x - data['amount']
                # calculates new y balance by keeping invariant constant
                new_y_balance = data['invariant'] / difference_of_x
                # uses function to get correct precision cost
                output_amount = self.correct_pool_amount(new_y_balance, self.amount_y.amount, unselected_asset)
                # assigns asset and correct cost to pool tracker variable
                pool_cost_track['pool_cost'] = output_amount
                pool_cost_track['asset'] = unselected_asset
            else:
                reference_y = self.amount_y.amount
                difference_of_y = reference_y - data['amount']
                new_x_balance = data['invariant'] / difference_of_y
                output_amount = self.correct_pool_amount(new_x_balance, self.amount_x.amount, unselected_asset)
                pool_cost_track['pool_cost'] = output_amount
                pool_cost_track['asset'] = unselected_asset
        else:
            if selected_asset == data['assets'][0]:
                reference_x = self.amount_x.amount
                addition_to_x = reference_x + data['amount']
                new_y_balance = data['invariant'] / addition_to_x
                output_amount = self.correct_pool_amount(self.amount_y.amount, new_y_balance, unselected_asset)
                pool_cost_track['pool_cost'] = output_amount
                pool_cost_track['asset'] = unselected_asset
            else:
                reference_y = self.amount_y.amount
                addition_to_y = reference_y + data['amount']
                new_x_balance = data['invariant'] / addition_to_y
                output_amount = self.correct_pool_amount(self.amount_x.amount, new_x_balance, unselected_asset)
                pool_cost_track['pool_cost'] = output_amount
                pool_cost_track['asset'] = unselected_asset
        pub.sendMessage('update_trading_prices', data={
            'pool': '{} {}'.format(pool_cost_track['pool_cost'], pool_cost_track['asset'])
        })

    def correct_market_precision(self, order_difference, price, asset, current_cost):
        precision = Asset(asset).precision
        Asset.clear_cache()
        unrounded_payout = order_difference * price
        unrounded_payout += current_cost
        return float(round(unrounded_payout, precision))

    def correct_pool_amount(self, higher_amount, lower_amount, asset):
        precision = Asset(asset).precision
        Asset.clear_cache()
        difference = higher_amount - lower_amount
        return float(round(difference, precision))

    def pool_change(self, data):
        self.get_blockchain_info(data)

    def take_offer(self, data):
        trade_message = ''
        new_data = {}
        try:
            bitshares = BitShares(node='wss://btsfullnode.bangzi.info/ws', nobroadcast=False, keys=data['key'], blocking='head')
            if data['market_or_pool'] == 'pool':
                new_data['operation_type'] = 'Pool Operation'
                if data['buy_or_sell'] == 'buy':
                    amount_to_sell = Amount(data['expected_price'])
                    new_data['anticipated'] = Amount('{} {}'.format(data['amount_to_buy_sell'], data['selected_asset']))
                    min_to_receive = new_data['anticipated'] * .993
                    trade_message = bitshares.exchange_with_liquidity_pool(
                        pool=data['pool_id'],
                        amount_to_sell=amount_to_sell,
                        min_to_receive=min_to_receive,
                        account=data['account'],
                    )
                else:
                    amount_to_sell = Amount('{} {}'.format(data['amount_to_buy_sell'], data['selected_asset']))
                    new_data['anticipated'] = Amount(data['expected_price'])
                    min_to_receive = new_data['anticipated'] * .993
                    trade_message = bitshares.exchange_with_liquidity_pool(
                        pool=data['pool_id'],
                        amount_to_sell=amount_to_sell,
                        min_to_receive=min_to_receive,
                        account=data['account'],
                    )
                new_data['operation_results'] = trade_message['operation_results']
                new_data['paid'] = Amount(new_data['operation_results'][0][1]['paid'][0])
                new_data['received'] = Amount(new_data['operation_results'][0][1]['received'][0])
        except:
            pass

        pub.sendMessage('print_transaction', data=new_data)

    def get_blockchain_info(self, asset):
        data = {'pool': asset}
        data['pool_object'] = self.bitshares.rpc.get_object(asset)
        data['pool_name'] = Asset(data['pool_object']['share_asset']).symbol
        data['asset_x'] = Asset(data['pool_object']['asset_a'])
        data['asset_y'] = Asset(data['pool_object']['asset_b'])
        data['amount_x'] = Amount(int(data['pool_object']['balance_a'])/10**data['asset_x'].precision, data['asset_x'])
        data['amount_y'] = Amount(int(data['pool_object']['balance_b'])/10**data['asset_y'].precision, data['asset_y'])
        self.amount_x = data['amount_x']
        self.amount_y = data['amount_y']
        data['market_ticker_object'] = Market(
            # python bitshares reverses base and quote
            base=data['asset_y'],
            quote=data['asset_x']
            ).ticker()
        data['market_orderbook'] = Market(
            base=data['asset_y'],
            quote=data['asset_x']
            ).orderbook(50)
        data['pool_invariant'] = int(data['pool_object']['virtual_value'])/(10**(data['asset_x'].precision + data['asset_y'].precision))

        # python bitshares reverses base and quote
        data['price_xy'] = Price(base=data['amount_y'], quote=data['amount_x'])
        data['price_yx'] = Price(base=data['amount_x'], quote=data['amount_y'])

        pub.sendMessage('update_gui', data=data)
