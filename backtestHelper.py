import backtrader as bt
import empyrical as emp
import numpy as np
from datetime import datetime
from collections import deque

def stock_to_bt(stock):
    for column in ["open", "high", "low"]:
        stock[column] = stock["close"]
    stock["volume"] = 0
    
    return bt.feeds.PandasData(dataname=stock)

class AssetAllocation(bt.Strategy):
    params = (
        ('pct_equity',[0.55, 0.45]),
        ('rebalance_period', 63),
        ('deposits', [[10000000000.00, datetime(2020, 1, 1)]])
    )
    def __init__(self):
        self.counter = 0
        self.initialized = False
        
    def next(self):
        # remove positions liquidated due to too high leverage
        # for d, pct in zip(self.datas, self.params.pct_equity):
        #     if d.close[0] == 0:
        #         holding = sum(bool(pos) for pos in self.getpositions().values())
        #         self.sell(d, size=holding)

        # buy shares on first day of portfolio open
        if not self.initialized and len(self.datas[0].open) >= 2:
            print("buying starting allocation")
            starting_cash = self.broker.get_value()
            purchase_shares = starting_cash // self.datas[0].open[1]
            print(f'buying {purchase_shares} shares of {self.datas[0]._name} for roughly ${starting_cash}')
            self.buy(self.datas[0], size=purchase_shares)
            self.initialized = True
                
        if self.counter % self.params.rebalance_period == 0:
            track_trades = dict()
            for d, pct in zip(self.datas, self.params.pct_equity):
                value = self.broker.get_value(datas=[d])
                if d.open[1] != 0:
                    allocation = value / self.broker.get_value()
                    units_to_trade = (pct - allocation) * self.broker.get_value() / d.open[1]
                    track_trades[d] = units_to_trade
            
            # Sell shares first
            for d, value in track_trades.items():
                if value < 0:
                    self.sell(d, size=value)
            
            # Buy shares second
            for d, value in track_trades.items():
                if value > 0:
                    self.buy(d, size=value)
        #print(f'current date: {self.datas[0].datetime.datetime()}\nupcoming deposits: {self.params.deposits}')
        if len(self.datas[0].open) >= 2 and self.params.deposits and self.params.deposits[0][1] <= self.datas[0].datetime.datetime(0):
            deposit = self.params.deposits.popleft()
            print(f'processing deposit {deposit[0]} on {self.datas[0].datetime.datetime()}')
            oldBalance = self.broker.get_value()
            print(f'old cash sweep balance: {oldBalance}')
            self.broker.add_cash(deposit[0])
            purchase_shares = int((oldBalance + deposit[0]) // self.datas[0].open[1])
            print(f'buying {purchase_shares} shares of {self.datas[0]._name} for roughly ${purchase_shares * self.datas[0].open[1]} with a balance of {oldBalance + deposit[0]}')
            self.buy(self.datas[0], size=purchase_shares)

        self.counter += 1

def backtest(datas, tickers, weights=[0.55, 0.45], rfr=0.105, plot=False, deposits=[[10000000000.00, datetime(2020, 1, 1)]], starting_value=1000):
    deposits = deque(sorted(deposits, key=lambda deposit: deposit[1]))
    nonzero_weight = np.argwhere(np.array(weights) != 0).flatten()
    weights_nonzero = [weights[i] for i in nonzero_weight]
    data_nonzero = [datas[i] for i in nonzero_weight]
    tickers_nonzero = [tickers[i] for i in nonzero_weight]

    cerebro = bt.Cerebro()
    for data, ticker in zip(data_nonzero, tickers_nonzero):
        cerebro.adddata(stock_to_bt(data), name=ticker)
		
    cerebro.broker.set_cash(starting_value)
    cerebro.broker.get_cash()
    cerebro.addanalyzer(bt.analyzers.PyFolio, _name='pyfolio')
    cerebro.addstrategy(AssetAllocation, **{'pct_equity' : weights_nonzero, 'deposits': deposits})
    results = cerebro.run(iplot=False)
	
    if plot:
        cerebro.plot(height=30)
		
    pyfoliozer = results[0].analyzers.getbyname('pyfolio')
    returns, positions, transactions, gross_lev = pyfoliozer.get_pf_items()
    return [
        emp.stats.max_drawdown(returns),
        emp.stats.annual_return(returns),
        emp.stats.cum_returns(returns)[-1],
        emp.stats.sharpe_ratio(returns, risk_free=rfr/252),
        emp.stats.sortino_ratio(returns, required_return=rfr/252),
        emp.stats.omega_ratio(returns, risk_free=rfr/252),
        emp.stats.calmar_ratio(returns),
    ]