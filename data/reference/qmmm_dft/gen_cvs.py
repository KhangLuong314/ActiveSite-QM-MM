#!/scratch/van/shared_envs/ambertools23/bin/python
import os
import sys
import numpy as np
import pytraj as pt


# label, atom mask 1 , atom mask 2, state A bond distance, state B bond ditance
masks = np.array([
    ['water exchange with WAT397', '1076', '1077', '1077', ':397@O']
])

n_windows = 42

parm = 'step3_pbcsetup.parm7'
cord = 'step3_pbcsetup.ncrst'
traj = pt.load(cord, parm)

for n in range(n_windows):
    fname = "../%02d/cv.rst" % n
    with open(fname, 'w') as f:
        for mask in masks:
            mlabel = mask[0]
            mask1 = mask[1]
            mask2 = mask[2]
            mask3 = mask[3]
            mask4 = mask[4]
            #dist1 = float(mask[3])
            #dist2 = float(mask[4])

            atm1 = traj.top.select(mask4)[0] + 1 
            #atm2 = traj.top.select(mask2)[0] + 1 
        
            f.write(f'# r1 - r2 {mlabel}\n')
            f.write(f' &rst\n')
            f.write(f'  iat={mask1},{mask2},{mask3},{atm1},\n')
            f.write(f'  rstwt=1.,-1.,\n')
            f.write(f'  r1=-20, r2=__REST__, r3=__REST__, r4=20,\n')                
            f.write(f'  rk2=150.0, rk3=150.0,\n')
            f.write(f' &end\n')
