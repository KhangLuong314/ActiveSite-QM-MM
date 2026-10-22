#!/bin/bash
#input file and setup simulation parameters

CV_i=-1.9
step=0.1

cwd=$(realpath ..)
inp_dir="${cwd}/input"

cd ${cwd}
n_windows=($(cat list))

for window in "${n_windows[@]}"; do

    echo "create: ${window}, ${inp_dir}/cv.rst"
    mkdir -p $window
    cd $window
    cp ${inp_dir}/cv.rst .

    nn=$(printf "%.3f" "${CV_i}")
    sed -i "s/__RST__/${nn}/g" cv.rst
    CV_i=$(echo $CV_i + $step | bc)

    cd ${cwd}
done
                            
