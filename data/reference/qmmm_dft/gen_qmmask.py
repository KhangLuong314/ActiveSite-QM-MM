#!/scratch/van/shared_envs/ambertools23/bin/python
import os
import sys
import numpy as np
import pytraj as pt

mask = [
    [ 'MG', ':372'],
    ['HIE', ':119'],
    ['GLN', ':139'],
    ['ASN', ':160'],
    ['WAT', ':496'],
    ['WAT', ':473'],
    ['WAT', ':491'],
    ['WAT', ':441'],
    [ 'DA',  ':34'],
    [ 'DG',  ':35']
]

