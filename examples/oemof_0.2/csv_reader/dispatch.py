# -*- coding: utf-8 -*-
"""
Dispatch optimisation using oemof's csv-reader.
"""

import os
import logging
import pandas as pd

from oemof.tools import logger
from oemof import solph
from oemof import outputlib
from matplotlib import pyplot as plt


def nodes_from_excel(filename):
    xls = pd.ExcelFile(filename)
    buses = xls.parse('buses')
    commodity_sources = xls.parse('commodity_sources')
    transformers = xls.parse('transformers')
    renewables = xls.parse('renewables')
    demand = xls.parse('demand')
    storages = xls.parse('storages')
    powerlines = xls.parse('powerlines')
    timeseries = xls.parse('time_series')

    # Create Bus objects from buses table
    busd = {}
    for i, b in buses.iterrows():
        busd[b['label']] = solph.Bus(label=b['label'])
        if b['excess']:
            solph.Sink(label=b['label'] + '_excess',
                       inputs={busd[b['label']]: solph.Flow()})
        if b['shortage']:
            solph.Source(label=b['label'] + '_shortage',
                         outputs={busd[b['label']]: solph.Flow(
                             variable_costs=b['shortage costs'])})

    # Create Source objects from table 'commodity sources'
    for i, cs in commodity_sources.iterrows():
        solph.Source(label=i, outputs={busd[cs['to']]: solph.Flow(
            variable_costs=cs['variable costs'])})

    # Create Source objects with fixed time series from 'renewables' table
    for i, re in renewables.iterrows():
        solph.Source(label=i, outputs={busd[re['to']]: solph.Flow(
            actual_value=timeseries[i], nominal_value=re['capacity'],
            fixed=True)})

    # Create Sink objects with fixed time series from 'demand' table
    for i, re in demand.iterrows():
        solph.Sink(label=i, inputs={busd[re['from']]: solph.Flow(
            actual_value=timeseries[i], nominal_value=re['maximum'],
            fixed=True)})

    # Create Transformer objects from 'transformers' table
    for i, t in transformers.iterrows():
        solph.Transformer(
            label=i,
            inputs={busd[t['from']]: solph.Flow()},
            outputs={busd[t['to']]: solph.Flow(
                nominal_value=t['capacity'], variable_costs=t['variable costs'],
                max=t['simultaneity'], fixed_costs=t['fixed costs'])},
            conversion_factors={busd[t['to']]: t['efficiency']})

    for i, s in storages.iterrows():
        solph.components.GenericStorage(
            label='storage',
            inputs={busd[s['bus']]: solph.Flow(
                nominal_value=s['capacity pump'], max=s['max'])},
            outputs={busd[s['bus']]: solph.Flow(
                nominal_value=s['capacity turbine'], max=s['max'])},
            nominal_capacity=s['capacity storage'],
            capacity_loss=s['capacity loss'],
            initial_capacity=s['initial capacity'],
            capacity_max=s['cmax'], capacity_min=s['cmin'],
            inflow_conversion_factor=s['efficiency pump'],
            outflow_conversion_factor=s['efficiency turbine'])

    for i, p in powerlines.iterrows():
        solph.Transformer(
            label='powerline_' + p['bus_1'] + '_' + p['bus_2'],
            inputs={busd[p['bus_1']]: solph.Flow()},
            outputs={busd[p['bus_2']]: solph.Flow(nominal_value=p['capacity'])},
            conversion_factors={busd[p['bus_2']]: p['efficiency']})
        solph.Transformer(
            label='powerline_' + p['bus_2'] + '_' + p['bus_1'],
            inputs={busd[p['bus_2']]: solph.Flow()},
            outputs={busd[p['bus_1']]: solph.Flow(nominal_value=p['capacity'])},
            conversion_factors={busd[p['bus_1']]: p['efficiency']})
    return busd


logger.define_logging()
datetime_index = pd.date_range(
    '2030-01-01 00:00:00', '2030-01-14 23:00:00', freq='60min')

# model creation and solving
logging.info('Starting optimization')

# initialisation of the energy system
es = solph.EnergySystem(timeindex=datetime_index)

# adding all nodes and flows to the energy system
# (data taken from excel-file)
nodes_from_excel(os.path.join(os.path.dirname(__file__), 'scenarios.xlsx',))

for n in es.nodes:
    print(n.label)

# creation of a least cost model from the energy system
om = solph.Model(es)
om.receive_duals()

# solving the linear problem using the given solver
om.solve(solver='cbc', solve_kwargs={'tee': True})

results = outputlib.processing.results(om)

region2 = outputlib.views.node(results, 'R2_bus_el')
region1 = outputlib.views.node(results, 'R1_bus_el')

print(region2['sequences'].sum())
print(region1['sequences'].sum())
region1['sequences'].plot()
plt.show()

logging.info("Done!")
