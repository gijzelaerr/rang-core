import numpy as np
from katbeam import JimBeam
b=JimBeam('MKAT-AA-L-JIM-2020')
for f in (990,1043,1097):
    r=np.linspace(0,3.0,3001)
    I=np.array([(b.I(x,0.0,f)+b.I(0.0,x,f))/2 for x in r])
    hp=r[np.argmax(I<0.5)]
    # first local minimum
    i=np.argmax((I[1:-1]<I[:-2])&(I[1:-1]<I[2:]))+1
    print(f,'FWHM deg',2*hp,'first null deg',r[i],I[i])
