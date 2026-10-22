# Chemistry engine: AmberTools 26 (sander QM/MM, sqm PM6, tleap, cpptraj, parmed, reduce) + GFN2-xTB.
# Native linux-aarch64 / linux-x86_64 builds from conda-forge.
FROM mambaorg/micromamba:1.5.10
RUN micromamba install -y -n base -c conda-forge ambertools=26.0 xtb=6.7.1 numpy pandas && micromamba clean -a -y
WORKDIR /work
ENTRYPOINT ["/usr/local/bin/_entrypoint.sh"]
