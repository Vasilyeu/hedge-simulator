"""Generates a list of historical event dates that may have had
significant impact on markets.  See extract_interesting_date_ranges.
"""

import datetime as dt
from collections import OrderedDict

import pandas as pd

PERIODS = OrderedDict()
# Dotcom bubble
PERIODS["Dotcom"] = (
    pd.Timestamp("20000310", tzinfo=dt.UTC),
    pd.Timestamp("20000910", tzinfo=dt.UTC),
)

# Lehmann Brothers
PERIODS["Lehman"] = (
    pd.Timestamp("20080801", tzinfo=dt.UTC),
    pd.Timestamp("20081001", tzinfo=dt.UTC),
)

# 9/11
PERIODS["9/11"] = (
    pd.Timestamp("20010911", tzinfo=dt.UTC),
    pd.Timestamp("20011011", tzinfo=dt.UTC),
)

# 05/08/11  US down grade and European Debt Crisis 2011
PERIODS["US downgrade/European Debt Crisis"] = (
    pd.Timestamp("20110805", tzinfo=dt.UTC),
    pd.Timestamp("20110905", tzinfo=dt.UTC),
)

# 16/03/11  Fukushima melt down 2011
PERIODS["Fukushima"] = (
    pd.Timestamp("20110316", tzinfo=dt.UTC),
    pd.Timestamp("20110416", tzinfo=dt.UTC),
)

# 01/08/03 US Housing Bubble 2003
PERIODS["US Housing"] = (
    pd.Timestamp("20030108", tzinfo=dt.UTC),
    pd.Timestamp("20030208", tzinfo=dt.UTC),
)

# 06/09/12  EZB IR Event 2012
PERIODS["EZB IR Event"] = (
    pd.Timestamp("20120910", tzinfo=dt.UTC),
    pd.Timestamp("20121010", tzinfo=dt.UTC),
)

# August 2007, March and September 2008, Q1 & Q2 2009,
PERIODS["Aug07"] = (
    pd.Timestamp("20070801", tzinfo=dt.UTC),
    pd.Timestamp("20070901", tzinfo=dt.UTC),
)
PERIODS["Mar08"] = (
    pd.Timestamp("20080301", tzinfo=dt.UTC),
    pd.Timestamp("20080401", tzinfo=dt.UTC),
)
PERIODS["Sept08"] = (
    pd.Timestamp("20080901", tzinfo=dt.UTC),
    pd.Timestamp("20081001", tzinfo=dt.UTC),
)
PERIODS["2009Q1"] = (
    pd.Timestamp("20090101", tzinfo=dt.UTC),
    pd.Timestamp("20090301", tzinfo=dt.UTC),
)
PERIODS["2009Q2"] = (
    pd.Timestamp("20090301", tzinfo=dt.UTC),
    pd.Timestamp("20090601", tzinfo=dt.UTC),
)

# Flash Crash (May 6, 2010 + 1-week post),
PERIODS["Flash Crash"] = (
    pd.Timestamp("20100505", tzinfo=dt.UTC),
    pd.Timestamp("20100510", tzinfo=dt.UTC),
)

# April and October 2014).
PERIODS["Apr14"] = (
    pd.Timestamp("20140401", tzinfo=dt.UTC),
    pd.Timestamp("20140501", tzinfo=dt.UTC),
)
PERIODS["Oct14"] = (
    pd.Timestamp("20141001", tzinfo=dt.UTC),
    pd.Timestamp("20141101", tzinfo=dt.UTC),
)

# Market down-turn in August/Sept 2015
PERIODS["Fall2015"] = (
    pd.Timestamp("20150815", tzinfo=dt.UTC),
    pd.Timestamp("20150930", tzinfo=dt.UTC),
)

# Market regimes
PERIODS["Low Volatility Bull Market"] = (
    pd.Timestamp("20050101", tzinfo=dt.UTC),
    pd.Timestamp("20070801", tzinfo=dt.UTC),
)

PERIODS["GFC Crash"] = (
    pd.Timestamp("20070801", tzinfo=dt.UTC),
    pd.Timestamp("20090401", tzinfo=dt.UTC),
)

PERIODS["Recovery"] = (
    pd.Timestamp("20090401", tzinfo=dt.UTC),
    pd.Timestamp("20130101", tzinfo=dt.UTC),
)

PERIODS["New Normal"] = (
    pd.Timestamp("20130101", tzinfo=dt.UTC),
    pd.Timestamp("20180921", tzinfo=dt.UTC),
)

PERIODS["Covid"] = (
    pd.Timestamp("20200211", tzinfo=dt.UTC),
    pd.Timestamp("20211231", tzinfo=dt.UTC),
)
