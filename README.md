# DKElectricity

A python package for getting data from [eloverblik.dk](https://eloverblik.dk) and [energidataservice.dk](https://energidataservice.dk) as pandas dataframes.

## Token

You need to create a token on [eloverblik.dk](https://eloverblik.dk) to access the data.

## Usage

```python
from datetime import datetime, timedelta
from dkelectricity import DKElectricity

# Token from eloverblik.dk
token = 'Your very long token'

el = DKElectricity(token)

# Dates of interest
to_data = datetime.today()
from_date = to_date + timedelta(weeks=-1)

# Get prices
prices = el.get_prices(from_date, to_date)

# Get consumption
consumption = el.get_consumption(from_date, to_date)

# Plot it
prices.plot(title=el.address, ylabel='Price [DKK]')
consumption.plot(title=el.address, ylabel='Consumption [kW]')
```

For more examples, see [notebooks](notebooks).

