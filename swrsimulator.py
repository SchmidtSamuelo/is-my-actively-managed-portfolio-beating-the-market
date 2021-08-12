import yfinance as yf
from datetime import date as dt
from datetime import datetime
import pandas as pd
import plotly
import plotly.graph_objects as go


class sustainable_withdrawal_rate:

    def __init__(self, ticker):
        # Retrieve the data from Yahoo Finance
        self.data = yf.download(tickers=ticker, period="max", interval='1mo')

        # Select the Adj Close column(s) from the retrieved data and store it into a dictionary
        self.closingdata = {}
        self.tickers = ticker.split(" ")

        # Data structure differs when there are multiple tickers downloaded
        if len(self.tickers) == 1:
            self.closingdata[self.tickers[0]] = self.data.loc[:, "Adj Close"]
        else:
            for tick in self.tickers:
                self.closingdata[tick] = self.data.loc[:, ("Adj Close", tick)].dropna()

        # Out of all the assets, determine the start year where data is available for all tickers
        start_year = []
        for key in self.closingdata:
            first_year = self.closingdata[key].index[0]
            # The starting point of the simulations are at the start of a year
            first_year = first_year.year if first_year.month == 1 else first_year.year + 1
            start_year.append(first_year)
        # Determine the max year
        self.start_year = max(start_year)

        # Select the last year with available data
        self.last_year = self.closingdata[self.tickers[0]].index[-1].year

        print("The historical period used for this analysis is from {} to {}.".format(self.start_year, self.last_year))
        print("The total amount of historical data used is {} years.".format(self.last_year - self.start_year + 1))

    def portfolio_success_rate(self, payout_period, asset_allocation):
        years_of_data = self.last_year - self.start_year + 1  # Including the start year
        # Store the tickers and their simulations in a nested dictionary
        self.nested_simulations = {}
        self.payout_period = payout_period

        # Iterate through all the tickers
        for key in self.closingdata:
            self.nested_simulations[key] = {}
            amount_of_simulations = 1
            # For each ticker, create the simulations
            for i in range(0, years_of_data):
                year = self.start_year + i
                max_year = year + payout_period

                if max_year > self.last_year:
                    break
                else:
                    self.nested_simulations[key]["Sim_" + str(i)] = self.closingdata[key][
                        (self.closingdata[key].index >= datetime.combine(dt(year, 1, 1), datetime.min.time())) &
                        (self.closingdata[key].index <= datetime.combine(dt(max_year, 1, 1),
                                                                         datetime.min.time()))].reset_index(drop=True)
                    amount_of_simulations += 1
        # Convert nested simulation to multiIndex dataframe
        reform = {(outerKey, innerKey): values for outerKey, innerDict in self.nested_simulations.items() for
                  innerKey, values in innerDict.items()}
        self.simulations = pd.DataFrame(reform)
        # Determine the percentage change between months
        returns = self.simulations.pct_change()
        # Adjust MultiIndex columns
        returns.columns = returns.columns.swaplevel(0, 1)
        returns.sort_index(axis=1, level=0, inplace=True)

        # Set the weights in the right order
        weight = []
        for asset in returns["Sim_0"].columns.values:
            weight.append(asset_allocation[asset])

        self.portfolio_returns = pd.DataFrame()
        # Determine the portfolio returns
        for simulation in range(0, amount_of_simulations - 1):
            # Determine the portfolio return based on the weights
            self.portfolio_returns["Sim_" + str(simulation)] = (returns["Sim_" + str(simulation)] * weight).sum(axis=1)

        success_rates = []
        for withdrawal in range(1, 13):
            success_rate = self.__calculate_succes_rate_for_withdrawals(withdrawal / 100, self.portfolio_returns)
            success_rates.append({"Annual withdrawal rate": withdrawal / 100,
                                  "Success rate": success_rate})
        success_rates = pd.DataFrame(success_rates)

        # Print out results
        print(success_rates)

    def __calculate_succes_rate_for_withdrawals(self, annual_withdrawal, returns, for_plot=False):

        portfolio_values = pd.DataFrame()
        # Annual withdrawal rate gets converted to monthly withdrawal rate
        monthly_withdrawal = annual_withdrawal / 12
        # Starting point of the portfolio
        port_val = [1]

        # Iterate through all the simulations to determine the portfolio value at every month
        for run in returns.columns.to_list():
            # Iterate through the different months in a simulation
            for index, row in returns[run].items():
                if index == 0:
                    pass
                else:
                    # Month-end portfolio values
                    vals = port_val[index - 1] * (1 + row) - port_val[0] * monthly_withdrawal
                    port_val.append(vals)
            # Add the portfolio values of a simulation to the portfolio_values dataframe
            portfolio_values[run] = port_val
            # Reset the starting portfolio_value for the next simulation
            port_val = [1]

        # Out of all the different scenarios, which simulated portfolio has a value greater than 0
        success_rate = sum(portfolio_values.iloc[-1, :] > 0) / portfolio_values.iloc[-1, :].count()
        if for_plot:
            return (portfolio_values)
        else:
            return (round(success_rate, 10))

    def plotsimulations(self, annual_withdrawal):

        # Retrieve the portfolio values for the simulations based on the withdrawal rate
        portfolio = self.__calculate_succes_rate_for_withdrawals(annual_withdrawal, self.portfolio_returns,
                                                                 for_plot=True)
        success = portfolio.iloc[-1] > 0
        success.reset_index(drop=True, inplace=True)

        # Convert portfolio from wide to long format for easier plotting
        portfolio.reset_index(inplace=True)
        portfolio = pd.wide_to_long(portfolio, stubnames="Sim_", i="index", j="SimulationId")
        # Reset index as this is a MultiIndex
        portfolio.reset_index(inplace=True)

        # Determine the list of colors
        colors = []
        for simulation in success:
            if simulation:
                colors.append("mediumseagreen")
            else:
                colors.append("lightcoral")

        fig = go.Figure()

        # Iterate through the simulations
        for i, v in success.items():
            temp = portfolio[portfolio["SimulationId"] == i]

            fig.add_trace(go.Scatter(x=temp["index"],
                                     y=temp["Sim_"],
                                     name="Simulation #{}".format(i),
                                     line=dict(color=colors[i])))

        fig.update_layout(
            title_text="Month-End Portfolio Value for simulations with a payout period of {} years and an annual withdrawal rate of {}".format(
                self.payout_period, annual_withdrawal),
            legend_title_text="Portfolio Simulations",
            yaxis=dict(title="Portfolio Value", zerolinecolor="black", rangemode="tozero"),
            xaxis=dict(title="Months"),
            width=1500,
            height=800)

        plotly.offline.plot(fig)
        print("Done")
