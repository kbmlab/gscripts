#!/bin/bash
#PBS -N test_qtools_submitter_wait_for_pbs
#PBS -o /Users/olga/workspace-git/YeoLab/gscripts/tests/data/test_qtools_submitter_wait_for_pbs.sh.out
#PBS -e /Users/olga/workspace-git/YeoLab/gscripts/tests/data/test_qtools_submitter_wait_for_pbs.sh.err
#PBS -V
#PBS -l walltime=0:01:00
#PBS -l nodes=1:ppn=16
#PBS -A yeo-group
#PBS -q home-yeo
#PBS -W depend=afterok:11111

# Go to the directory from which the script was called
cd $PBS_O_WORKDIR
date
echo testing PBS

