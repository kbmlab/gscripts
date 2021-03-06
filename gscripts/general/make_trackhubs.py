#!/usr/bin/python
'''
reated on Mar 7, 2013

@author: gabrielp

Given a list of * files makes trackhubs for those files

Assumes that you have passwordless ssh setup between the two servers you are transfering files from

'''

import argparse
import re
import os
from itertools import groupby

from trackhub import Hub, GenomesFile, Genome, TrackDb, Track, AggregateTrack, SuperTrack
from trackhub.upload import upload_track, upload_hub

def remove_special_chars(string):
    return re.sub(r'[%+]+', '', string)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Takes in files to turn into trackhub')
    parser.add_argument(
        'files', nargs='+',
        help='Files to turn into track hub')
    parser.add_argument('--genome', help="genome use", required=True)
    parser.add_argument('--hub', help="hub name, (no spaces)", required=True)
    parser.add_argument('--short_label', default=None,
                        help="short label for hub")
    parser.add_argument('--long_label', default=None, help="long label for hub")
    parser.add_argument('--num_sep', default=2, type=int, help="Number of seperators deep to group on")
    parser.add_argument('--sep', default=".", help="Seperator")
    parser.add_argument('--email', default='gpratt@ucsd.edu',
                        help="email for hub")
    parser.add_argument('--server', default="sauron.ucsd.edu",
                        help="server to SCP to")
    parser.add_argument('--user', default='gpratt',
                        help="that is uploading files")
    parser.add_argument('--no_s3', default=True, action="store_false",
                        help="upload to defined server instead of s3")
    parser.add_argument('--upload_dir', default='', help="directory to upload files to if not uploading to aws")
    args = parser.parse_args()

    #default setting
    if not args.short_label:
        args.short_label = args.hub
    if not args.long_label:
        args.long_label = args.short_label

    upload_dir = os.path.join(args.upload_dir, args.hub)
    #THIS IS REALLY BAD AND NOT INUITITVE
    if args.no_s3:
        URLBASE = os.path.join("https://s3-us-west-1.amazonaws.com/sauron-yeo/", args.hub) 
    else:
        URLBASE = os.path.join("http://sauron.ucsd.edu/Hubs", args.hub)
       
    GENOME = args.genome

    hub = Hub(hub=args.hub,
              short_label=args.short_label,
              long_label=args.long_label,
              email=args.email,
    )

    genomes_file = GenomesFile()
    genome = Genome(GENOME)
    trackdb = TrackDb()
    supertrack = SuperTrack(name=args.hub,
                            short_label=args.hub,
                            long_label=args.hub)
    genome.add_trackdb(trackdb)
    genomes_file.add_genome(genome)
    hub.add_genomes_file(genomes_file)
    hub.upload_fn = upload_dir

    files = args.files
    #logic for doing pos and neg as the same multi trackhub
    #process bw files first, do the rest with old logic
    bw_files = [track for track in files if
                track.endswith(".bw") or track.endswith(".bigWig")]
    remaining_files = [track for track in files if
                       not (track.endswith(".bw") or track.endswith(".bigWig"))]

    key_func = lambda x: x.split(args.sep)[:args.num_sep]

    for bw_group, files in groupby(sorted(bw_files, key=key_func), key_func):
        files = list(files)
        
        print bw_group, files


        long_name = remove_special_chars(os.path.basename(args.sep.join(bw_group[:args.num_sep])))
        aggregate = AggregateTrack(
            name=long_name,
            tracktype='bigWig',
            short_label=long_name,
            long_label=long_name,
            aggregate='transparentOverlay',
            showSubtrackColorOnUi='on',
            autoScale='on',
            priority='1.4',
            alwaysZero='on',
            visibility="full"
            )
        
        for track in files:
            base_track = remove_special_chars(os.path.basename(track))
            
            color = "0,100,0" if "pos" in track else "100,0,0"
            
            if track.endswith(".bw") or track.endswith('.bigWig'):
                tracktype = "bigWig"
            if track.endswith(".bb") or track.endswith('.bigBed'):
                tracktype = "bigBed"
            if track.endswith(".bam"):
                tracktype = "bam"
            
            split_track = base_track.split(args.sep)
            
            long_name = args.sep.join(split_track[:args.num_sep] + split_track[-3:])
            track = Track(
                name= long_name,
                url = os.path.join(URLBASE, GENOME, base_track),
                tracktype = tracktype,
                short_label=long_name,
                long_label=long_name,
                color = color,
                local_fn = track,
                remote_fn = os.path.join(upload_dir, GENOME, base_track)
                )
            
            aggregate.add_subtrack(track)
        supertrack.add_track(aggregate)
        #trackdb.add_tracks(aggregate)
    
    bigBed_files = [track for track in remaining_files if track.endswith(".bb") or track.endswith(".bigBed")]

    for bigBed_file in bigBed_files:
        color = "0,100,0" if "pos" in bigBed_file else "100,0,0"
        base_track = remove_special_chars(os.path.basename(bigBed_file))
        long_name = args.sep.join(base_track.split(args.sep)[:args.num_sep]) + ".bb"
        track = Track(
            name=long_name,
            url=os.path.join(URLBASE, GENOME, base_track),
            tracktype="bigBed",
            short_label=long_name,
            long_label=long_name,
            color=color,
            local_fn=bigBed_file,
            remote_fn=os.path.join(upload_dir, GENOME, base_track),
            visibility="full"
        )
        #trackdb.add_tracks(track)
        supertrack.add_track(track)
    trackdb.add_tracks(supertrack)
    result = hub.render()
    hub.remote_fn = os.path.join(upload_dir, "hub.txt")

    for track in trackdb.tracks:
        upload_track(track=track, host=args.server, user=args.user, run_s3=args.no_s3)

    upload_hub(hub=hub, host=args.server, user=args.user, run_s3=args.no_s3)
