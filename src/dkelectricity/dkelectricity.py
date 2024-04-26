import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import json


def get_prices(from_date, to_date, area='DK1'):
    # Get price data as json
    url = 'https://api.energidataservice.dk/dataset/Elspotprices'
    params = {
        'start': from_date.strftime("%Y-%m-%d"),
        'end': to_date.strftime("%Y-%m-%d"),
        'filter': f'{{"PriceArea": "{area}"}}',
        'columns': 'HourDK,SpotPriceDKK',
        'sort': 'HourDK'
    }

    response = requests.get(url, params)
    response.raise_for_status()

    data = response.json().get('records', [])

    # Make a nice dataframe
    generator = ([datetime.strptime(
        d['HourDK'], '%Y-%m-%dT%H:%M:%S'), d['SpotPriceDKK']] for d in data)
    df = pd.DataFrame(generator, columns=['Time', 'Price'])
    df.set_index('Time', inplace=True)

    # Drop duplicates (when changing from summer to winter time)
    df = df[~df.index.duplicated()]

    # Interpolate (when changing from winter to summer time)
    df = df.resample('H').interpolate()

    # Convert price to DKK/kWh incl. VAT
    df['Price'] *= 0.00125

    return df


class DKElectricity:
    _base_url = 'https://api.eloverblik.dk/CustomerApi/api/'
 
    def __init__(self, refresh_token):
        self._access_token = self._get_access_token(refresh_token)
 
        # Create header for get and post calls
        self._header = {'Authorization': 'Bearer ' + self._access_token,
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'}
 
        self._metering_point, self._address = self._get_metering_point_and_address()
 
        # Create body for post calls
        self._body = {"meteringPoints": {"meteringPoint": [self._metering_point]}}
 
        self._tariffs = self._get_tariffs()
 
    def _get_access_token(self, refresh_token):
        response = requests.get(self._base_url + 'Token', headers={'Authorization': 'Bearer ' + refresh_token}, timeout=15)
        response.raise_for_status()
        return response.json()['result']
    
    def _get_metering_point_and_address(self):
        # Get first metering point
        response = requests.get(self._base_url + 'meteringpoints/meteringpoints', headers=self._header)
        response.raise_for_status()
        address = response.json()['result'][0]['streetName'] + ' ' + response.json()['result'][0]['buildingNumber']
        metering_point = response.json()['result'][0]['meteringPointId']
        return metering_point, address

    def _get_tariffs(self):
        url = self._base_url + f'meteringpoints/meteringpoint/getcharges'

        response = requests.post(url, data=json.dumps(self._body), headers=self._header, timeout=60)
        response.raise_for_status()

        data = response.json()['result'][0]['result']['tariffs']

        total = np.zeros((24,))

        for d in data:
            tariff = np.empty((0))
            for p in d['prices']:
                tariff = np.append(tariff, p['price'])

            total += tariff

        # Add VAT
        total *= 1.25

        tariffs = pd.DataFrame({'Hour': np.arange(24, dtype=int), 'Tariff': total})
        tariffs.set_index('Hour', inplace=True)

        return tariffs
    
    @property
    def tariffs(self):
        return self._tariffs

    @property
    def address(self):
        return self._address

    def get_prices(self, from_date, to_date, area='DK1'):
        # Get price data as json
        url = 'https://api.energidataservice.dk/dataset/Elspotprices'
        params = {
            'start': from_date.strftime("%Y-%m-%d"),
            'end': to_date.strftime("%Y-%m-%d"),
            'filter': f'{{"PriceArea": "{area}"}}', 
            'columns': 'HourDK,SpotPriceDKK',
            'sort': 'HourDK'
        }

        response = requests.get(url, params)
        response.raise_for_status()

        data = response.json().get('records', [])

        # Make a nice dataframe
        generator = ([datetime.strptime(d['HourDK'], '%Y-%m-%dT%H:%M:%S'), d['SpotPriceDKK']] for d in data)
        df = pd.DataFrame(generator, columns=['Time', 'Price'])
        df.set_index('Time', inplace=True)
        
        # Drop duplicates (when changing from summer to winter time)
        df = df[~df.index.duplicated()]

        # Interpolate (when changing from winter to summer time)
        df = df.resample('h').interpolate()

        # Convert price to DKK/kWh incl. VAT
        df['Price'] *= 0.00125

        # Add tariffs
        if True:
            df['Hour'] = df.index.hour
            df = df \
                .set_index('Hour', append=True) \
                .add(self._tariffs.rename(columns={'Tariff': 'Price'})) \
                .reset_index(1)
            df.drop(columns='Hour', inplace=True)

        return df

    def get_consumption(self, from_date, to_date):
        # Don't try to look into the future (the API doesn't support it)
        tomorrow = datetime.today() + timedelta(days=1)
        to_date = to_date if to_date <= tomorrow else tomorrow

        url = self._base_url + f'meterdata/gettimeseries/{from_date.strftime("%Y-%m-%d")}/{to_date.strftime("%Y-%m-%d")}/Hour'

        response = requests.post(url, data=json.dumps(self._body), headers=self._header, timeout=60)
        response.raise_for_status()

        data = response.json()['result'][0]['MyEnergyData_MarketDocument']['TimeSeries'][0]['Period']
        
        # Check the resolution
        all(d['resolution'] == 'PT1H' for d in data)

        time_format = '%Y-%m-%dT%H:%M:%SZ'
        to_datetime = lambda start, hour : datetime.strptime(start, time_format) + timedelta(hours=hour)

        generator = ([to_datetime(day['timeInterval']['start'], h), float(hour['out_Quantity.quantity'])] for day in data for h, hour in enumerate(day['Point']))

        df = pd.DataFrame(generator, columns=['Time', 'Consumption'])
        df.set_index('Time', inplace=True)

        # Convert from UTC to DK time and remove localization again, so duplicate removal and interpolation will work
        df = df.tz_localize('UTC').tz_convert('Europe/Copenhagen').tz_localize(None)

        # Drop duplicates (when changing from summer to winter time)
        df = df[~df.index.duplicated()]

        # Interpolate (when changing from winter to summer time)
        df = df.resample('h').interpolate()

        return df