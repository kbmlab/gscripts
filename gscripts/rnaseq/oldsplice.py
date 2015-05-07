from __future__ import division
import re
import pysam
from clipper.src.peaks import readsToWiggle_pysam
import sys
import os
from subprocess import Popen, call, PIPE
from optparse import OptionParser, SUPPRESS_HELP
from numpy import *
from multiprocessing import Pool
#from deap import dtm
import cPickle as pickle
import random
import pybedtools

__author__ = "Michael Lovci"




def region_rpk(interval, bam):
    chrom, start, stop, strand = (interval.chrom,interval.start,
                                  interval.stop, interval.strand)
    readCount = bam.count(reference=chrom, start=start, end=stop) #this is not strand-ed
    Kb = len(interval)/1000
    return readCount/Kb


def assign_reads(gene, splicedict=None, bam_file=None,
                 alignment_slop=10, flip=True, splicetypes=None):

    if splicedict is None or bam_file is None:

        raise Exception
    bam_fileobj = pysam.Samfile(bam_file, 'rb')
    data = {}
    
    chrom = splicedict["chromosome"]
    strand = splicedict["strand"]
    tx_start = splicedict["tx_start"]
    tx_end = splicedict["tx_end"]
    
    signstrand = None

    if flip is True:
        usestrand = strand * -1
    else:
        usestrand = strand

    if usestrand == 1:
        signstrand = "+"

    elif usestrand == -1:
        signstrand = "-"


    interval = pybedtools.Interval(chrom, tx_start, tx_end, strand=signstrand)
    subset_reads = bam_fileobj.fetch(reference=chrom, start=tx_start,end=tx_end)
    
    (wig, jxns, nrCounts, readLengths, 
     reads) = readsToWiggle_pysam(subset_reads, (tx_start-1000),
                                  (tx_end+1000), signstrand, "center", False)
    
    data["descriptor"] = gene
    if "SE" in splicedict and "SE" in splicetypes:
        data["SE"] = {}
        for loc in splicedict["SE"]:
            #rangestart = splicedict[gene]["SE"][loc]["rangestart"]
            #rangeend = splicedict[gene]["SE"][loc]["rangeend"]                
            data["SE"][loc] = {}
            data["SE"][loc]["IN"] = 0
            data["SE"][loc]["EX"] = 0

            bodyLoc = splicedict['SE'][loc]["BODY"]
            upLoc = splicedict['SE'][loc]["UP"]
            downLoc = splicedict['SE'][loc]["DOWN"]
            if strand == 1:
                upIntronLoc = upLoc.split("-")[1] + "-" + bodyLoc.split("-")[0]
                downIntronLoc = bodyLoc.split("-")[1] + "-" +  downLoc.split("-")[0]
            else:
                upIntronLoc = bodyLoc.split("-")[1] + "-" + upLoc.split("-")[0]
                downIntronLoc = downLoc.split("-")[1] + "-" +  bodyLoc.split("-")[0]
            
            try:
                data["SE"][loc]["BODY_RPK"] = region_rpk(pybedtools.Interval(chrom, *map(int, bodyLoc.split("-")), strand=signstrand), bam_fileobj)

                data["SE"][loc]["UP_RPK"] = region_rpk(pybedtools.Interval(chrom, *map(int, upLoc.split("-")), strand=signstrand), bam_fileobj)

                data["SE"][loc]["DOWN_RPK"] = region_rpk(pybedtools.Interval(chrom, *map(int, downLoc.split("-")), strand=signstrand), bam_fileobj)

                data["SE"][loc]["UPI_RPK"] = region_rpk(pybedtools.Interval(chrom, *map(int, upIntronLoc.split("-")), strand=signstrand), bam_fileobj)

                data["SE"][loc]["DOWNI_RPK"] = region_rpk(pybedtools.Interval(chrom, *map(int, downIntronLoc.split("-")), strand=signstrand), bam_fileobj)
            except:
                #import pdb; pdb.set_trace()
                print "uh oh %s" %(gene + loc)
                continue

            for structure in splicedict["SE"][loc]["IN"]:
                if structure.startswith("j"):
                    structurestrip = structure.lstrip("j")
                    
                    structurestrip = tuple(map(int, structurestrip.split(":")))

                    if structurestrip in jxns:
                        data["SE"][loc]["IN"] += jxns[structurestrip]


            for structure in splicedict["SE"][loc]["EX"]:
                if structure.startswith("j"):
                    structurestrip = structure.lstrip("j")
                    structurestrip = tuple(map(int, structurestrip.split(":")))                    
                    if structurestrip in jxns:
                        data["SE"][loc]["EX"] += jxns[structurestrip]

    if "MXE" in splicedict and "MXE" in splicetypes:
        data["MXE"] = {}
#        for loc in splicedict[gene]["MXE"]:
        for loc in splicedict["MXE"]:            
            #rangestart = splicedict[gene]["SE"][loc]["rangestart"]
            #rangeend = splicedict[gene]["SE"][loc]["rangeend"]                
            data["MXE"][loc] = {}
            data["MXE"][loc]["A"] = 0
            data["MXE"][loc]["B"] = 0
            #import code
            #code.interact(local=locals())
            for structure in splicedict["MXE"][loc]["A"]:
                if structure.startswith("j"):
                    structurestrip = structure.lstrip("j")
                    structurestrip = tuple(map(int, structurestrip.split(":")))                    
                    if structurestrip in jxns:
                        data["MXE"][loc]["A"] += jxns[structurestrip]
                elif structure.startswith("b"):
                    continue
                    exstart, exstop = map(int, structure.lstrip("b").split("-"))
                    for position in range(exstart, (exstop+1)):
                        if position in reads:
                            for read_end in reads[position]:
                                if read_end <= exstop:
                                    data["MXE"][loc]["A"] += reads[position][read_end]

            for structure in splicedict["MXE"][loc]["B"]:
                if structure.startswith("j"):
                    structurestrip = structure.lstrip("j")
                    structurestrip = tuple(map(int, structurestrip.split(":")))                    
                    if structurestrip in jxns:
                        data["MXE"][loc]["B"] += jxns[structurestrip]
                elif structure.startswith("b"):
                    continue
                    exstart, exstop = map(int, structure.lstrip("b").split("-"))
                    for position in range(exstart, (exstop+1)):
                        if position in reads:
                            for read_end in reads[position]:
                                if read_end <= exstop:
                                    data["MXE"][loc]["B"] += reads[position][read_end]                                    

    return data

def overlap(coord, locs, ov = .95):
    """returns index of locs that overlap > ov% with coord"""
    chr1, x1y1 = coord.split(":")
    x1, y1 = map(int, x1y1.split("-"))

    ovExons = []

    for i, loc in enumerate(locs):
        chr2, x2y2 = loc.split(":")
        if chr1 != chr2:
            continue
        x2, y2 = map(int, x2y2.split("-"))
        if y1 >= x2 and x1 <= y2:

            v = sorted([x1,y1,x2,y2])
            overlap = (v[2] - v[1])+1/((y1 - x1)+1.)
            if overlap >= ov:
                ovExons.append(i)
    return ovExons
            


                         


def retrieve_splicing(species):

    host = Popen(["hostname"], stdout=PIPE).communicate()[0].strip()
    if "optiputer" in host or "compute" in host:
        basedir = "/nas/nas0/yeolab/Genome/ensembl/AS_STRUCTURE/" + species + "data4/"
    elif "tcc" in host or "triton" in host:
        basedir = "/projects/yeolab/Genome/ensembl/AS_STRUCTURE/" + species + "data4/"
    elif "tscc" in host:
        basedir = "/projects/ps-yeolab/lovci/AS_STRUCTURE/gencode/" + species + "data4/"
    else:
        print "Where am I?"
        basedir = os.path.join(os.environ['GENOME'], "AS_STRUCTURE", "gencode",  species + "data4")
        assert os.path.exists(basedir)

    try:
        info= pickle.load(open((basedir + species + ".spliceDict_simple.pickle")))
    except:
        if species == "hg19":
            chrs = map(str,range(1,23)) #1-22
            chrs.append("X")
            chrs.append("Y")
        elif species == "mm9":
            chrs = map(str,range(1,20)) #1-19
            chrs.append("X")
            chrs.append("Y")        
        info = dict()
        for chr in chrs:
            ASfile = basedir + species + ".tx." + chr + ".AS.STRUCTURE"
            f = open(ASfile, "r")
            annotline = f.next()
            eof = False
            while not eof:
                blank, gene, chromosome, transcripts, d2, d3, d4, strand, numex, exonloc, intronloc, exonlen, intronlen, asSplicingType, locSplicingType = annotline.strip().split("\t")

                numbered = {}
                numberedR = {}
                exons = exonloc.rstrip("|").split("|")
                exonNumbers = range(1, len(exons)+1)

                if strand == -1:
                    exonNumbers = exonNumbers[::-1]

                for exon, number in zip(exons, exonNumbers):
                    numbered[exon] = number
                    numberedR[number] = exon


                info[gene] = {}
                info[gene]["chromosome"] = "chr" + chr
                info[gene]["strand"] = int(strand)
                info[gene]["tx_start"] = min(map(int, exonloc.rstrip("|").replace("|", "-").split("-")))
                info[gene]["tx_end"] = max(map(int, exonloc.rstrip("|").replace("|", "-").split("-")))
                line = f.next().strip()
                if line.startswith("<"):
                    while True:
                        try:
                            splicing_labels = f.next().strip()
                        except:
                            eof = True
                            break
                        if splicing_labels.startswith(">"):
                            annotline = splicing_labels
                            break
                        loc, splicingType, inorout, labels = splicing_labels.split("\t")
                        exonIndexes = overlap(chromosome + ":" + loc, map(lambda x: chromosome + ":" + x, exons))
                        if len(exonIndexes) > 1:
                            raise Exception
                        try:

                            exN = numbered[exons[exonIndexes[0]]]
                            thisExonNumber = gene + "|" +  str(exN - 1) #convert to 0-based exon numbers

                        except:
                            continue
                            
                        if splicingType is "OV" or splicingType is "RI":
                            continue                    # skip RI and OV... not well defined yet

                        if not splicingType in info[gene]:
                            info[gene][splicingType] = {}

    #I know the "pass" statements are verbose.
                        if "SE" in splicingType:
     


                            exNUp = exN - 1
                            try:
                                upLoc = numberedR[exNUp]
                                exNDn = exN + 1
                                dnLoc = numberedR[exNDn]
                            except:
                                event = gene + " Exon %d" %(exN)
                                print "Failed to index this event: %s" %(event)
                                continue


                            if not loc in info[gene][splicingType]:
                                info[gene][splicingType][loc] = {}
                                info[gene][splicingType][loc]['prettyName'] = thisExonNumber
                                info[gene][splicingType][loc]["rangestart"] = 10000000000000
                                info[gene][splicingType][loc]["rangeend"] = -10000000000000
                                info[gene][splicingType][loc]["bedTrack"] = str()
                                #if not loc in numbered:
                                #    import code
                                #    code.interact(local=locals())                                   
                                #exN= numbered[loc]
                                #prevN = exN-1
                                #nextN = exN+1
                                #misoXref = ":".join([gene, str(prevN), str(exN), str(nextN)])
                                
                                #info[gene][splicingType][loc]["misoXref"] = misoXref

                                info[gene][splicingType][loc]["IN"] = {}
                                info[gene][splicingType][loc]["EX"] = {}
                                info[gene][splicingType][loc]["BODY"] = None
                                info[gene][splicingType][loc]["UP"] = None
                                info[gene][splicingType][loc]["DOWN"] = None
                            seen = {}
                            versions = labels.rstrip("|").split("|")
                            for v in versions:
                                transcript, vstrand, locUp, locIn, locDown, evidence = v.split(":")

                                if int(vstrand) == -1:
                                    locDown, locUp = locUp, locDown
                                info[gene][splicingType][loc]["rangestart"] = min(info[gene][splicingType][loc]["rangestart"], (int(locUp)+1))
                                info[gene][splicingType][loc]["rangeend"] = max(info[gene][splicingType][loc]["rangeend"], (int(locDown)+1))


                                info[gene][splicingType][loc]["UP"] = upLoc
                                info[gene][splicingType][loc]["DOWN"] = dnLoc


                                if "IN" in inorout:
                                    if info[gene][splicingType][loc]["BODY"]:
                                        x = info[gene][splicingType][loc]["BODY"]
                                        x1, x2 = x.split('-')
                                        y1, y2 = locIn.split('-')
                                        (x1, x2, y1, y2) = map(int, [x1, x2, y1, y2]) 
                                        if (y2 - y1) > (x2-x1): #if this exon body is bigger than previous versions of this exon, update.
                                            info[gene][splicingType][loc]["BODY"] = locIn                                            
                                    else:
                                        info[gene][splicingType][loc]["BODY"] = locIn
                                    exstart, exstop = map(str, locIn.split("-"))

                                    try:
                                        info[gene][splicingType][loc][inorout]["j" + locUp + ":" + str(int(exstart)+1)] += 1#upstream jxn
                                    except:
                                        info[gene][splicingType][loc][inorout]["j" + locUp + ":" + str(int(exstart)+1)] = 1#upstream jxn
                                    try:
                                        info[gene][splicingType][loc][inorout]["j" + exstop + ":" + str(int(locDown)+1)] += 1#dnstream jxn
                                    except:
                                        info[gene][splicingType][loc][inorout]["j" + exstop + ":" + str(int(locDown)+1)] = 1 #dnstream jxn
                                else:
                                    #import code
                                    #code.interact(local=locals())
                                    try:
                                        info[gene][splicingType][loc][inorout]["j" + locUp + ":" + str(int(locDown)+1)] += 1
                                    except:
                                        info[gene][splicingType][loc][inorout]["j" + locUp + ":" + str(int(locDown)+1)] = 1
                            if int(strand) == 1:
                                signstrand = "+"
                            else:
                                signstrand = "-"
                            info[gene][splicingType][loc]["bedTrack"] = "\t".join([("chr" + chr), str(info[gene][splicingType][loc]["rangestart"]), str(info[gene][splicingType][loc]["rangeend"]), (gene), "1", signstrand])

                        elif "MXE" in splicingType:
                            #define A or B with varied 5' and 3' exon termini
                            
                            if not loc in info[gene][splicingType]:
                                info[gene][splicingType][loc] = {}
                                info[gene][splicingType][loc]['prettyName'] = thisExonNumber                                                            
                                info[gene][splicingType][loc]["A"] = {}
                                info[gene][splicingType][loc]["B"] = {}
                                info[gene][splicingType][loc]["rangestart"] = 100000000000
                                info[gene][splicingType][loc]["rangeend"] = -100000000000                            

                            versions = labels.rstrip("|").split("|")
                            for v in versions:
                                transcript, vstrand, locUp, locIn, locDown, evidence = v.split(":")
                                if int(vstrand) == -1:
                                    locDown, locUp = locUp, locDown
                                    pass
                                info[gene][splicingType][loc]["rangestart"] = min(info[gene][splicingType][loc]["rangestart"], int(locUp))
                                info[gene][splicingType][loc]["rangeend"] = max(info[gene][splicingType][loc]["rangeend"], int(locDown))                            

                                if "IN" in inorout:
                                    try:
                                        info[gene][splicingType][loc]["A"]["b" + locIn] += 1#body
                                    except:
                                        info[gene][splicingType][loc]["A"]["b" + locIn] = 1#body
                                    exstart, exstop = locIn.split("-")
                                    try:
                                        info[gene][splicingType][loc]["A"]["j" + locUp + ":" + str(int(exstart)+1)] += 1#upstream jxn
                                    except:
                                        info[gene][splicingType][loc]["A"]["j" + locUp + ":" + str(int(exstart)+1)] = 1 #upstream jxn
                                    try:
                                        info[gene][splicingType][loc]["A"]["j" + exstop + ":" + str(int(locDown)+1)] +=1 #dnstream jxn
                                    except:
                                        info[gene][splicingType][loc]["A"]["j" + exstop + ":" + str(int(locDown) +1)] =1 #dnstream jxn
                                    pass
                                else:
                                    try:
                                        info[gene][splicingType][loc]["B"]["b" + locIn] += 1#body
                                    except:
                                        info[gene][splicingType][loc]["B"]["b" + locIn] = 1#body
                                    exstart, exstop = locIn.split("-")
                                    try:
                                        info[gene][splicingType][loc]["B"]["j" + locUp + ":" + str(int(exstart)+1)] +=1#upstream jxn
                                    except:
                                        info[gene][splicingType][loc]["B"]["j" + locUp + ":" + str(int(exstart)+1)] =1#upstream jxn
                                    try:
                                        info[gene][splicingType][loc]["B"]["j" + exstop + ":" + str(int(locDown)+1)] +=1#dnstream jxn
                                    except:
                                        info[gene][splicingType][loc]["B"]["j" + exstop + ":" + str(int(locDown)+1)] =1#dnstream jxn
                            if int(strand) == 1:
                                signstrand = "+"
                            else:
                                signstrand = "-"
                            info[gene][splicingType][loc]["bedTrack"] = "\t".join([("chr" + chr), str(info[gene][splicingType][loc]["rangestart"]), str(info[gene][splicingType][loc]["rangeend"]), (gene), "1", signstrand])                                    

                        elif "A5E" in splicingType or "A3E" in splicingType:
                            if not loc in info[gene][splicingType]: 
                                info[gene][splicingType][loc] = {}                           
                                info[gene][splicingType][loc]['jxns'] = {}
                                info[gene][splicingType][loc]["rangestart"] = 100000000000
                                info[gene][splicingType][loc]["rangeend"] = -100000000000                            

                            versions = labels.rstrip("|").split("|")
                            for v in versions:
                                transcript, vstrand, locUp, locIn, locDown, evidence = v.split(":")
                                if int(vstrand) == -1:
                                    locDown, locUp = locUp, locDown
                                info[gene][splicingType][loc]["rangestart"] = min(info[gene][splicingType][loc]["rangestart"], int(locUp))
                                info[gene][splicingType][loc]["rangeend"] = max(info[gene][splicingType][loc]["rangeend"], int(locDown))                                                        
                                exstart, exstop = locIn.split("-")                            
                                jxns = [("j" + locUp + ":" + str(int(exstart)+1)), ("j" + exstop + ":" + str(int(exstop)+1))]
                                for jxn in jxns:
                                    try:
                                        info[gene][splicingType][loc]['jxns'][jxn] +=1
                                    except:
                                        info[gene][splicingType][loc]['jxns'][jxn] =1

        pickle.dump(info, file=open( (basedir + species + ".spliceDict_simple.pickle"), "w"))
    return info


    return data
import multiprocessing        
from multiprocessing import Pool
def mapper(f, argList, np=multiprocessing.cpu_count()):
    """ map a function with a list of several args """

    p = Pool(processes=np)

    mapper = [p.apply_async(f, args =args) for args in argList]
    [mapped.wait() for mapped in mapper]
    data = []
    for i, mapped in enumerate(mapper):
        if mapped.successful():
            data.append(mapped.get())
        else:
            sys.stderr.write("unsucessful\t%s" %argList[i][0])
            data.append(None)
    p.close()

    return data


def main(options):
    species = options.species

    bamfile = options.bam
    splicetypes = options.splicetypes
    if splicetypes is None:
        print "you must specify what type of splicing to examine: SE/MXE are implemented now"
    

    splicing = retrieve_splicing(species)
    if options.exitOnBuild:
        exit()
    if options.gene is not None:
        genes = options.gene
    else:
        genes = splicing.keys()
    
    if options.maxgenes is not None:
        if not options.maxgenes > len(genes):
            genes = random.sample(genes, options.maxgenes)


    def funcStar(args):
        rtrn = assign_reads(*args)
        return rtrn

    args = []
    for g in genes:
        args.append([g, splicing[g], bamfile, options.slop, options.flip, splicetypes])
    debug = options.debug
    data = list()
    if debug:
        for arg in args:

            data.append(assign_reads(*arg))
    else:
        data = mapper(assign_reads, args, np = options.np)
    
    st = "_".join(splicetypes)
    if options.outfile is None:
        outfile = os.path.join(options.prefix, (bamfile.replace(".bam", ".splices.pickle") + "." + st))
    else:
        outfile = options.outfile


    with open(outfile, 'w') as o_f:
        pickle.dump(data, file=o_f)




    #AS, splicingTypes  = bulid_AS_STRUCTURE_dict("mm9")
    #SE_list = list()
    #find SE exons, convert to a usable format
    #for gene in AS:
    #    for exonSplicingType in AS[gene]['splicingTypes']:
    #        isoforms
    #        if "SE" in exonSplicingType:
    #other exon splicingTypes...

    
if __name__ == "__main__":
    usage = "oldsplice.py --bam file.bam --species <species> --splice_type SE --splice_type MXE --outfile file.pickle [-f]"
    description = "Given a bam file, count reads to isoforms. comparisons come later"
    parser = OptionParser(usage=usage, description=description)
    parser.add_option("--bam", '-b', dest="bam", help = "bam file")
    parser.add_option("--species", '-s', dest="species")
    parser.add_option("--outfile", '-o', dest="outfile", default=None)
    parser.add_option("--flip", '-f', dest="flip", default=False, action="store_true", help="flip read strand")
    parser.add_option("--prefix", dest="prefix", default=os.getcwd(), help="output location")
    parser.add_option("--processors",  dest="np", type="int", default=multiprocessing.cpu_count(), help="number of processors to use")
    parser.add_option("--splice_type", dest="splicetypes", default=None, action="append")
    parser.add_option("--slop", dest="slop", default=0, help=SUPPRESS_HELP)#help="alignment slop tolerance (for overhangs)") #not implemented


    parser.add_option("--debug", dest="debug", default=False, action="store_true", help="run in debug mode")
    parser.add_option("--gene", dest="gene", default=None, action="append", type="str")
    parser.add_option("--maxgenes", dest="maxgenes", type="int", default=None)    
    parser.add_option("--exitOnBuild", dest="exitOnBuild", default=False, action="store_true")    

    (options,args) = parser.parse_args()
    baiFile = options.bam + ".bai"

    import subprocess
    if not os.path.exists(baiFile):
        print "indexing bam file"
        subprocess.call(["samtools", "index", options.bam])
    
    main(options)

    exit()
                
    
