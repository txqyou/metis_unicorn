"""
PHONEY [Pronounce 'poney'], Partitioning of Hypergraph Obviously Not EasY

Want to use it? Then check the 'HMETIS_PATH' and 'dirs' variables.

Note: It is very important at the moment that the clusters have the same ID as their
position in the Graph.clusters list.
"""

"""
TODO
> Doc
> Change the ID of the clusters so that it begins at 1 instead of 0.
"""

import math
from subprocess import call
import copy
import matplotlib.pyplot as plt
import threading
from multiprocessing import Process, Pipe
import time
import pickle
import random

global HMETIS_PATH
HMETIS_PATH = "/home/para/dev/metis_unicorn/hmetis-1.5-linux/"
METIS_PATH = "/home/para/dev/metis_unicorn/metis/bin/"
PATOH_PATH = "/home/para/Downloads/patoh/build/Linux-x86_64/"
ALGO = 1 # 0: METIS
         # 1: PaToH
# EDGE_WEIGHTS_TYPES = 10
EDGE_WEIGHTS_TYPES = 1
VERTEX_WEIGHTS_TYPES = 1
WEIGHT_COMBILI_COEF = 0.5
MAX_WEIGHT = 1000
THREADS = 7     # Amount of parallel process to use when building the hypergraph.
CLUSTER_INPUT_TYPE = 0  # 0: standard .out lists
                        # 1: Ken's output
                        # 2: Custom clustering, no boundaries
SIMPLE_GRAPH = False    # False: hypergraph, using hmetis
                        # True: standard graph, using gpmetis
MEMORY_BLOCKS = False   # True if there are memory blocks (bb.out)
IMPORT_HYPERGRAPH = True    # True: import the hypergraph from a previous dump,
                            # skip the graph building directly to the partitioning.
DUMP_FILE = 'hypergraph.dump'
# DUMP_FILE = 'simplegraph.dump'

HETEROGENEOUS_FACTOR = 5 #

RANDOM_SEED = 0 # 0: no seed, pick a new one
                # other: use this

DUMMY_CLUSTER = False # Add a dummy cluster (low area, high power)
DUMMY_NAME = "dummy_cluster"
POWER_ASYMMETRY = 80    # [50; 100]
                        # At 50: symmetry
                        # At 100: evrything in one partition
MANUAL_ASYMMETRY = False # Execute a manual asymmetrisation of the power across partitions.

POWER_DENSITIES = [1.0, 0.6, 0.45, 0.42, 0.39, 0.22, 0.18, 0.11, 0.10, 0.08, 0.08, 0.05, 0.05]

def printProgression(current, max):
    progression = ""
    if current == max/10:
        progression = "10%"
    elif current == max/5:
        progression = "20%"
    elif current == 3*max/10:
        progression = "30%"
    elif current == 2*max/5:
        progression = "40%"
    elif current == max/2:
        progression = "50%"
    elif current == 3*max/5:
        progression = "60%"
    elif current == 7*max/10:
        progression = "70%"
    elif current == 4*max/5:
        progression = "80%"
    elif current == 9*max/10:
        progression = "90%"
    elif current == max:
        progression = "100%"
    return progression


def buildHyperedges(processID, startIndex, endIndex, nets, clusters, pipe):

    hyperedges = []
    print "in process"
    # print clusters
    i = startIndex
    while i < endIndex:
        net = nets[i]
        connectedClusters = list() # List of clusters.

        # Now, for each net, we get its list of instances.
        for netInstance in net.instances: # netInstance are Instance object.

            # And for each instance in the net, we check to which cluster
            # that particular instance belongs.
            for cluster in clusters:
                # Try to find the instance from the net in the cluster
                if cluster.searchInstance(netInstance):
                    # If found, see if the cluster has already been added
                    # to connectedClusters.
                    j = 0
                    clusterFound = False
                    while j < len(connectedClusters) and not clusterFound:
                        if connectedClusters[j].ID == cluster.ID:
                            clusterFound = True
                        else:
                            j += 1
                    if not clusterFound:
                        connectedClusters.append(cluster)

        # Append the list A of connected clusters to the list B of hyperedges
        # only if there are more than one cluster in list A.
        if len(connectedClusters) > 1:
            if SIMPLE_GRAPH:
                for k in xrange(0,len(connectedClusters)):
                    for l in xrange(k + 1, len(connectedClusters)):
                        hyperedge = Hyperedge()
                        hyperedge.addCluster(connectedClusters[k])
                        hyperedge.addCluster(connectedClusters[l])
                        hyperedge.addNet(net)
                        hyperedges.append(hyperedge)
            else:
                hyperedge = Hyperedge()
                for cluster in connectedClusters:
                    # print cluster
                    hyperedge.addCluster(cluster)
                hyperedge.addNet(net)
                hyperedges.append(hyperedge)

        progression = printProgression(i - startIndex, endIndex - startIndex)
        if progression != "":
            print "Process " + str(processID) + " " + progression
        i += 1


    pipe.send(hyperedges)
    pipe.close()

def closeEnough(target, value):
    tolerance = 0.2
    if value < (target + tolerance*target) and \
        value > (target - tolerance*target):
        return True
    else:
        return False

def elementIsInList(element, theList):
    found = False
    try:
        theList.index(element)
    except:
        pass
    else:
        found = True
    return found



class Graph():
    def __init__(self):
        self.clusters = [] # list of Cluster objects
        self.nets = [] # list of Net objects.
        self.hyperedges = []
        self.hyperedgeWeightsMax = []   # Maximum weight for each weight type.
                                        # Ordered by weight type.
        self.partitions = []    # Each element is a list of clusters (objects)
                                # included in the corresponding cluster.
        self.partitionsArea = []
        self.partitionsPower = []
        self.logfilename = "graph.log"
        call(["rm","-rf","graph.log"])

    def WriteLog(self, obj):
        f = open(self.logfilename, "a")
        f.write(str(obj)+"\n")
        f.close()

    def findClusterByName(self, clusterName):
        found = False
        clusterID = 0
        while not found and clusterID < len(self.clusters):
            if self.clusters[clusterID].name == clusterName:
                found = True
            else:
                clusterID += 1
        return found, clusterID

    def ReadClusters(self, filename, hrows, frows):
        print (str("Reading clusters file: " + filename))
        with open(filename, 'r') as f:
            lines = f.read().splitlines()

        # Remove the header lines
        for i in xrange(0, hrows):
            del lines[0]
        # Remove the footer lines
        for i in xrange(0,frows):
            del lines[-1]

        if CLUSTER_INPUT_TYPE == 0:
            for i, line in enumerate(lines):
                line = line.strip(' \n')
                clusterDataRow = line.split()
                cluster = Cluster(clusterDataRow[0], i, False)

                lowerBounds = clusterDataRow[3][1:-1].split(",")    # Exclude the first and last
                                                                    # chars: '(' and ')'.
                upperBounds = clusterDataRow[4][1:-1].split(",")
                cluster.setBoundaries(float(lowerBounds[0]), float(lowerBounds[1]),
                    float(upperBounds[0]), float(upperBounds[1]))

                cluster.setArea(float(clusterDataRow[5]))
                self.clusters.append(cluster)
        elif CLUSTER_INPUT_TYPE == 1:
            for i, line in enumerate(lines):
                line = line.strip(' \n')
                clusterDataRow = line.split()
                cluster = Cluster(clusterDataRow[0], i, False)
                cluster.setArea(clusterDataRow[1])
                self.clusters.append(cluster)
        elif CLUSTER_INPUT_TYPE == 2:
            for i, line in enumerate(lines):
                line = line.strip(' \n')
                clusterDataRow = line.split()
                cluster = Cluster(clusterDataRow[0], i, False)

                cluster.setArea(float(clusterDataRow[4]))
                self.clusters.append(cluster)


    def readClustersInstances(self, filename, hrows, frows):
        # print "--------------------------------------------------->"
        print (str("Reading clusters instances file: " + filename))
        with open(filename, 'r') as f:
            lines = f.read().splitlines()

        if CLUSTER_INPUT_TYPE == 0:
            # Remove the header lines
            for i in xrange(0, hrows):
                del lines[0]
            # Remove the footer lines
            for i in xrange(0,frows):
                del lines[-1]

            for line in lines:
                line = line.strip(' \n')
                line = line.replace('{','')
                line = line.replace('}','')
                # print line
                clusterInstancesRow = line.split()
                found, clusterID = self.findClusterByName(clusterInstancesRow[0])
                if found:
                    del clusterInstancesRow[0]
                    for i, instanceName in enumerate(clusterInstancesRow):
                        # instance = Instance(instanceName)
                        # self.clusters[clusterID].addInstance(instance)
                        self.clusters[clusterID].addInstance(instanceName)
        elif CLUSTER_INPUT_TYPE == 1:
            # line sample : add_to_cluster -inst lb/rtlc_I2820 c603
            for i, line in enumerate(lines):
                line = line.strip(' \n')
                clusterInstancesRow = line.split()
                found, clusterID = self.findClusterByName(clusterInstancesRow[3])
                if found:
                    foundInstance = self.clusters[clusterID].searchInstance(clusterInstancesRow[2])
                    if not foundInstance:
                        self.clusters[clusterID].addInstance(clusterInstancesRow[2])
                else:
                    print "Das ist ein Problem, cluster " + clusterInstancesRow[3] + " not found."
                progression = printProgression(i, len(lines))
                if progression != "":
                    print progression



    def readMemoryBlocks(self, filename, hrows, frows):
        print (str("Reading memory blocks file: " + filename))
        with open(filename, 'r') as f:
            lines = f.read().splitlines()

        # Remove the header lines
        for i in xrange(0, hrows):
            del lines[0]
        # Remove the footer lines
        for i in xrange(0,frows):
            del lines[-1]

        for i in xrange(0, len(lines)):
            lines[i] = " ".join(lines[i].split())

        i = 0
        existingClustersCount = len(self.clusters) # Clusters already in the list before.
        blockCount = 0
        while i < len(lines):
            line = lines[i]
            #[0]: block name
            #[2]: instance count
            #[4]: physical area
            #[10]: instance
            blockRow = line.split()
            # print blockRow
            if len(line) > 0:
                if CLUSTER_INPUT_TYPE == 0:
                    memoryBlock = Cluster(blockRow[10], existingClustersCount + blockCount, True)
                    blockCount += 1
                    moduleArea = float(blockRow[4])
                    memoryBlock.setArea(moduleArea)
                    memoryBlock.addInstance(blockRow[10])
                    self.clusters.append(memoryBlock)

                    for j in xrange(1, int(blockRow[2])):
                        i += 1
                        line = lines[i]
                        subBlockRow = line.split()
                        memoryBlock = Cluster(subBlockRow[1], existingClustersCount + blockCount, True)
                        blockCount += 1
                        memoryBlock.setArea(moduleArea)
                        memoryBlock.addInstance(subBlockRow[1])
                        self.clusters.append(memoryBlock)

                elif CLUSTER_INPUT_TYPE == 1:
                    moduleArea = float(blockRow[4])
                    k = 0
                    found = False
                    while k < len(self.clusters) and not found:
                        cluster = self.clusters[k]
                        found = cluster.searchInstance(blockRow[10])
                        if found:
                            cluster.setArea(moduleArea)
                            cluster.blackbox = True
                        k += 1

                    for j in xrange(1, int(blockRow[2])):
                        i += 1
                        line = lines[i]
                        subBlockRow = line.split()
                        l = 0
                        found = False
                        while l < len(self.clusters) and not found:
                            cluster = self.clusters[l]
                            found = cluster.searchInstance(subBlockRow[1])
                            if found:
                                cluster.setArea(moduleArea)
                                cluster.blackbox = True
                            l += 1


            i += 1
            progression = printProgression(i, len(lines))
            if progression != "":
                print progression


    def readNetsWireLength(self, filename, hrows, frows):
        print (str("Reading wire length nets file: " + filename))
        with open(filename, 'r') as f:
            lines = f.read().splitlines()

        # Remove the header lines
        for i in xrange(0, hrows):
            del lines[0]
        # Remove the footer lines
        for i in xrange(0,frows):
            del lines[-1]

        for i in xrange(0, len(lines)):
            lines[i] = " ".join(lines[i].split())
        lines.sort()

        for i, line in enumerate(lines):
            netDataRow = line.split()

            net = Net(netDataRow[0], i)
            net.setPinAmount(int(netDataRow[1]))
            net.setWL(int(float(netDataRow[2])) + 1)    # + 1 here to make sure
                                                        #we don't use a net with WL = 0
            self.nets.append(net)
            progression = printProgression(i, len(lines))
            if progression != "":
                print progression


    def readNets(self, filename, hrows, frows):
        print (str("Reading nets file: " + filename))
        with open(filename, 'r') as f:
            lines = f.read().splitlines()

        # Remove the header lines
        for i in xrange(0, hrows):
            del lines[0]
        # Remove the footer lines
        for i in xrange(0,frows):
            del lines[-1]

        lines.sort()

        # As the nets list is sorted, we should not run through all the
        # self.nets list for each line.
        # For each line, move forward in self.nets. If the net in the line
        # is found, great! If not, no biggie, just keep moving forward.
        netID = 0
        i = 0
        while i < len(lines) and netID < len(self.nets):
            line = lines[i]
            line = line.strip(' \n')
            line = line.replace('{','')
            line = line.replace('}','')
            netDataRow = line.split()
            if self.nets[netID].name == netDataRow[0]:
                del netDataRow[0]
                for instanceName in netDataRow:
                    # instance = Instance(instanceName)
                    # self.nets[netID].addInstance(instance)
                    self.nets[netID].addInstance(instanceName)
                netID += 1
            i += 1

            progression = printProgression(i, len(lines))
            if progression != "":
                print progression


    def findHyperedges(self):
        print "Building hyperedges"

        processes = []
        pipes = []
        print "Before processes"
        # print self.clusters

        for i in xrange(0, THREADS):
            parent_pipe, child_pipe = Pipe()
            pipes.append(parent_pipe)
            process = Process(target=buildHyperedges, args=(i, \
                i * len(self.nets) / THREADS, \
                (i + 1) * len(self.nets) / THREADS, \
                self.nets, \
                self.clusters, \
                child_pipe,))
            process.start()
            processes.append(process)

        for i, pipe in enumerate(pipes):
            print "Waiting pipe from process " + str(i)
            hyperedges = pipe.recv()
            for hyperedge in hyperedges:
                self.hyperedges.append(hyperedge)

        for process in processes:
            process.join()




        s = ""
        for hyperedge in self.hyperedges:
            s += str(len(hyperedge.clusters)) + "\t" + str(hyperedge.nets[0].name)
            for cluster in hyperedge.clusters:
                s += " " + str(cluster.name)
            s += "\n"
        with open("raw_hyperedges.out", 'w') as f:
            f.write(s)


        print "Merging hyperedges"
        i = 0
        while i < len(self.hyperedges):
            hyperedgeA = self.hyperedges[i]
            duplicate = False
            clusterAMerged = False  # Flag set in case an hyperedgeA is merged
                                    # into an hyperedgeB.
            j = i + 1
            while j < len(self.hyperedges) and not clusterAMerged:
                hyperedgeB = self.hyperedges[j]
                if len(hyperedgeA.clusters) == len(hyperedgeB.clusters):
                    duplicate = True
                    k = 0
                    # Check if all clusters in the hyperedge are the same
                    while k < len(hyperedgeA.clusters) and duplicate:
                        clusterA = hyperedgeA.clusters[k]
                        clusterB = hyperedgeB.clusters[k]
                        if clusterA.name != clusterB.name:
                            duplicate = False
                        else:
                            k += 1
                    if duplicate:
                        # Append the net from hyperedgeB to hyperedgeA.
                        # At this point, hyperedgeB only has one edge.
                        hyperedgeA.addNet(hyperedgeB.nets[0])
                        hyperedgeA.connectivity += 1
                        del self.hyperedges[j]
                    else:
                        j += 1

                else:
                    j += 1

            # If hyperedgeA has not been merged, inspect the next one.
            # Otherwise, hyperedgeA has been deleted and all the following
            # elements have been shifted, thus no need to increment the index.
            if not clusterAMerged:
                i += 1

            progression = printProgression(i, len(self.hyperedges))
            if progression != "":
                print progression

        if SIMPLE_GRAPH:
            print "Prepare simple graph"
            # print self.clusters
            for i, hyperedge in enumerate(self.hyperedges):
                for k, clusterA in enumerate(hyperedge.clusters):
                    # Due to the fact that the hyperedges come from another process,
                    # the objects in hyperedge.clusters and self.clusters do not point
                    # to the same element anymore.
                    clusterA = self.clusters[clusterA.ID]
                    for l, clusterB in enumerate(hyperedge.clusters):
                        clusterB = self.clusters[clusterB.ID]
                        if l != k:
                            clusterA.connectedClusters.append(clusterB.ID)
                            clusterA.connectedEdges.append(hyperedge)
                    # print len(clusterA.connectedClusters)




    def generateMetisInput(self, filename, edgeWeightType, vertexWeightType):
        print "Generating METIS input file..."
        s = ""
        if SIMPLE_GRAPH:
            s = str(len(self.clusters)) + " " + str(len(self.hyperedges)) + " 011"

            if VERTEX_WEIGHTS_TYPES > 1:
                s += " " + str(VERTEX_WEIGHTS_TYPES)

            for i, cluster in enumerate(self.clusters):
                # print cluster
                s += "\n"
                for weightType in xrange(0, VERTEX_WEIGHTS_TYPES):
                    s += str(cluster.weightsNormalized[weightType]) + " "
                for j in xrange(0, len(cluster.connectedClusters)):
                    s += " " + str(cluster.connectedClusters[j] + 1) + \
                        " " + str(cluster.connectedEdges[j].weightsNormalized[edgeWeightType])


        else:
            s = str(len(self.hyperedges)) + " " + str(len(self.clusters)) + " 11"
            for i, hyperedge in enumerate(self.hyperedges):
                s += "\n" + str(hyperedge.weightsNormalized[edgeWeightType]) + " "
                for cluster in hyperedge.clusters:
                    s += str(cluster.ID + 1) + " "  # hmetis does not like to have hyperedges
                                                    # beginning with a cluster of ID '0'.
            for cluster in self.clusters:
                s += "\n" + str(cluster.weightsNormalized[vertexWeightType])
        with open(filename, 'w') as file:
            file.write(s)


    def generatePaToHInput(self, filename, edgeWeightType, vertexWeightType):
        print "Generating PaToH input file..."
        s = ""

        # Compute the amount of 'pins' in the hypergraph.
        # For PaToH, a pin is a vertex in a hyperedge.
        # So to compute this amount, we simply need to now how
        # many vertex (cluster, here) are in each hyperedge.
        pins = 0
        for hyperedge in self.hyperedges:
            pins += len(hyperedge.clusters)

        # TODO add the possibility to have all the vertex weights types in the same description (PaToH can do that).
        s = "1 " + str(len(self.clusters)) + " " + str(len(self.hyperedges)) + " " + str(pins) + " 3" + " 1"
        for i, hyperedge in enumerate(self.hyperedges):
            s += "\n" + str(hyperedge.weightsNormalized[edgeWeightType]) + " "
            for cluster in hyperedge.clusters:
                s += str(cluster.ID + 1) + " "

        s += "\n"

        for cluster in self.clusters:
            s += str(cluster.weightsNormalized[vertexWeightType]) + " "

        s += "\n" # Requires a new line at the end of the file.

        with open(filename, 'w') as file:
            file.write(s)


    def computeHyperedgeWeights(self, normalized):
        print "Generating weights of hyperedges."

        self.hyperedgeWeightsMax = [0] * EDGE_WEIGHTS_TYPES
        for weightType in xrange(0, EDGE_WEIGHTS_TYPES):
            for i, hyperedge in enumerate(self.hyperedges):
                weight = 0
                if weightType == 0:
                    # Number of wires
                    weight = hyperedge.connectivity
                elif weightType == 1:
                    # 1/#wires
                    weight = 1.0 / hyperedge.weights[0]
                elif weightType == 2:
                    # Total wire length
                    for net in hyperedge.nets:
                        weight += net.wl
                elif weightType == 3:
                    # 1/Total wire length
                    weight = 1.0 / hyperedge.weights[2]
                elif weightType == 4:
                    # Average wire length
                    wlTot = 0
                    for net in hyperedge.nets:
                        wlTot += net.wl
                    wlAvg = wlTot / len(hyperedge.nets)
                    weight = wlAvg
                elif weightType == 5:
                    # 1/Average wire length
                    weight = 1.0 / hyperedge.weights[4]
                elif weightType == 6:
                    # Number of wires * total length
                    weight = hyperedge.weights[0] * hyperedge.weights[2]
                elif weightType == 7:
                    weight = 1.0 / hyperedge.weights[6]
                elif weightType == 8:
                    # total wire length and number of wires
                    weight = \
                        WEIGHT_COMBILI_COEF * hyperedge.weightsNormalized[0] + \
                        (1 - WEIGHT_COMBILI_COEF) * hyperedge.weightsNormalized[1]
                elif weightType == 9:
                    # 1 / total wire length and number of wires
                    weight = 1 / hyperedge.weights[8]


                hyperedge.setWeight(weightType, weight)
                # Save the max
                if weight > self.hyperedgeWeightsMax[weightType]:
                    self.hyperedgeWeightsMax[weightType] = weight

            # Normalize
            for hyperedge in self.hyperedges:
                hyperedge.setWeightNormalized(weightType, int(((hyperedge.weights[weightType] * MAX_WEIGHT) / self.hyperedgeWeightsMax[weightType])) + 1)




    # def findSmallestCluster(self, clusters):
    #     smallest = clusters[0].area
    #     smallestID = 0
    #     for i, cluster in enumerate(clusters):
    #         if cluster.area < smallest:
    #             smallest = cluster.area
    #             smallestID = i

    #     return smallestID

    def computeClustersPower(self):
        '''
        For each cluster, set a random power density.
        The power of the cluster is thus its density * its area.
        '''
        for cluster in self.clusters:
            powerDensity = random.uniform(1, HETEROGENEOUS_FACTOR)
            power = cluster.area * powerDensity
            cluster.setPowerDensity(powerDensity)
            cluster.setPower(power)
            # print "Power density = " + str(powerDensity) + \
            #     ", area = " + str(cluster.area) + \
            #     ", power = " + str(power)
            cluster.setPowerDensity(powerDensity)
            cluster.setPower(power)


    def computeVertexWeights(self):
        print "Generating weights of vertices."
        self.clusterWeightsMax = [0] * VERTEX_WEIGHTS_TYPES
        totalPower = 0
        totalNormalizedPower = 0

        for weightType in xrange(0, VERTEX_WEIGHTS_TYPES):
            # Weight = cluster area
            if weightType == 0:
                for cluster in self.clusters:
                    weight = cluster.area

                    if weight > self.clusterWeightsMax[weightType]:
                        self.clusterWeightsMax[weightType] = weight

                    cluster.setWeight(weightType, weight)
                    # print str(weight)

            # Weight = cluster power
            elif weightType == 1:

                for cluster in self.clusters:
                    weight = cluster.power
                    totalPower += weight
                    cluster.setWeight(weightType, weight)

                    if weight > self.clusterWeightsMax[weightType]:
                        self.clusterWeightsMax[weightType] = weight

        # Normalization
        for cluster in self.clusters:
            for weightType in xrange(0, VERTEX_WEIGHTS_TYPES):
                weight = ((cluster.weights[weightType] * MAX_WEIGHT) / self.clusterWeightsMax[weightType]) + 1
                cluster.setWeightNormalized(weightType, int(weight))
                if weightType == 1:
                    totalNormalizedPower += cluster.weightsNormalized[weightType]
            # print cluster.weightsNormalized


        if DUMMY_CLUSTER:
            # Append the dummy cluster to the cluster list.
            dummy = Cluster(DUMMY_NAME, len(self.clusters), False)
            # If we want 70/30 asymmetry, the dummy power will be
            # totalNormalizedPower * 0.4, using 40 % of one partition's power
            dummyPower = totalNormalizedPower * (POWER_ASYMMETRY - (100 - POWER_ASYMMETRY)) / 100
            print "totalNormalizedPower: " + str(totalNormalizedPower) + \
                ", dummyPower: " + str(dummyPower)
            dummy.setArea(0.1)
            dummy.setPower(dummyPower)
            dummy.setWeight(0, 0.1)
            dummy.setWeight(1, dummy.power)
            dummy.setWeightNormalized(0, 1)
            dummy.setWeightNormalized(1, dummy.power)
            dummy.setDummy(True)
            self.clusters.append(dummy)



    def GraphPartition(self, filename):
        '''
        Call the hmetis command with the given filename, or gpmetis if we are working
        with simple graphs.
        '''

        print "--------------------------------------------------->"
        # print "Running partition on cost: ", CostFunction
        print "Running hmetis with " + filename
        # call(["/Users/drago/bin/hmetis-1.5-osx-i686/hmetis",filename,"2","5","20","1","1","1","0","0"])
        # hmetis graphFile Nparts UBfactor Nruns Ctype Rtype Vcycle Reconst dbglvl
        Nparts = 2
        UBfactor = 1
        Nruns = 20
        Ctype = 1
        Rtype = 1
        Vcycle = 1
        Reconst = 0
        dbglvl = 8
        command = ""
        if SIMPLE_GRAPH:
            command = METIS_PATH + "gpmetis " + filename + " 2 -dbglvl=0 -ufactor=30"
        else:
            command = HMETIS_PATH + "hmetis " + filename + " " + str(Nparts) + \
                " " + str(UBfactor) + " " + str(Nruns) + " " + str(Ctype) + " " + \
                str(Rtype) + " " + str(Vcycle) + " " + str(Reconst) + " " + str(dbglvl)
            print "Calling '" + command + "'"
        # call([HMETIS_PATH + "hmetis",filename,"2","5","20","1","1","1","0","0"])
        call(command.split())


    def GraphPartitionPaToH(self, filename):
        print "--------------------------------------------------->"
        print "Running PaToH with " + filename
        command = PATOH_PATH + "patoh " + filename + " 2 RA=6 UM=U OD=3"
        call(command.split())


    def WritePartitionDirectives(self, metisFileIn, metisFileOut):
        '''
        Create the partition directives in .tcl files.
        This is the final output telling which module (cluster) is going on which die.
        '''
        # print "--------------------------------------------------->"
        print "Write tcl file for file: ", metisFileIn
        try:
            fOut = open(metisFileOut, "w")
            fIn = open(metisFileIn, "r")
        except IOError as e:
            print "Can't open file"
            return False

        # Find the longest cluster name first.
        # This is necessary in order to align the 'Diex' part
        # of the .tcl directives, allowing to apply easy column
        # edits later on.
        maxLength = 0
        for cluster in self.clusters:
            if len(cluster.name) > maxLength:
                maxLength = len(cluster.name)


        data = fIn.readlines()
        if ALGO==1: # In PaToH, everything is on one single line.
            data = data[0].split()

        for i, cluster in enumerate(self.clusters):
            s = ""
            # Comment the dummy cluster out.
            if cluster.name == DUMMY_NAME:
                s += "#"
            if cluster.blackbox:
                s += "add_to_die -inst    " + str(cluster.name) + \
                    " " * (maxLength - len(cluster.name)) + \
                    " -die Die" + str(data[i])
            else:
                s += "add_to_die -cluster " + str(cluster.name) + \
                    " " * (maxLength - len(cluster.name)) + \
                    " -die Die" + str(data[i])
            if ALGO==1:
                s+= "\n"

            fOut.write(s)
        fOut.close()
        fIn.close()
        print "Done!"
        # print "<---------------------------------------------------\n"

    def dumpClusters(self):
        s = "ID -- Cluster -- Area -- Power density -- Power"
        # print "len(self.clusters) = " + str(len(self.clusters))
        for cluster in self.clusters:
            s += str(cluster.ID) + "\t" + cluster.name + "\t" + str(cluster.area) + "\t" + \
                str(cluster.powerDensity) + "\t" + str(cluster.power) + "\n"
        with open("clusters", 'w') as f:
            f.write(s)

    def hammingReport(self, filenames):
        '''
        As the output for a bipartition is either 0 or 1 (depending on which die a cluster is
        assigned to), by comparing the output of two different partition (e.g. based on different
        weights) for the same clusters, we can compute some sort of Hamming distance between
        them.
        This metric caracterize the difference bewteen two bipartitions.
        '''
        partitions = []
        table = ""

        part = 0
        for filename in filenames:
            # Print the header, but ommit '0'
            if part > 0:
                table += str(part)# Table header
            table += "\t"
            part += 1

            with open(filename, 'r') as f:
                lines = f.read().splitlines()
                for i in xrange(0, len(lines)):
                    lines[i] = lines[i].strip(' \n')
                partitions.append(lines)
                # print lines

        table += "\n"

        for i in xrange(0, len(partitions) - 1): # ommit the last line, it has already been done as the last column
            table += str(i) + "\t" # Row name
            table += "\t" * i
            for j in xrange(i + 1, len(partitions)):
                hammingDistance = 0
                for bit in xrange(0, len(partitions[i])):
                    if partitions[i][bit] != partitions[j][bit]:
                        hammingDistance += 1
                # Hamming distance normalized, limited to two decimal points
                table += str("%.2f" % (float(hammingDistance)/len(partitions[i]))) + "\t"
            table += "\n"

        part = 0
        table += "Legend:\n"
        for filename in filenames:
            table += str(part) + ":\t" + filename + "\n"
            part += 1
        print table



    def plotWeights(self):
        # weights = [0] * EDGE_WEIGHTS_TYPES
        weights = []
        styles = ['b', 'r', 'g', 'c', 'm', 'y', 'k']
        for i in xrange(0, EDGE_WEIGHTS_TYPES):
            weights.append(list())
        for hyperedge in self.hyperedges:
            for i in xrange (0, EDGE_WEIGHTS_TYPES):
                weights[i].append(hyperedge.weightsNormalized[i])
        print weights[0]
        for i in xrange(0, EDGE_WEIGHTS_TYPES):
            plt.plot(weights[i], styles[i])
        plt.show()


    def computePartitionArea(self):

        self.partitionsArea = [0] * 2

        for i, partition in enumerate(self.partitions):
            for cluster in partition:
                self.partitionsArea[i] += cluster.area

        totalArea = 0
        for part in self.partitionsArea:
            totalArea += part

        areaFraction = [0] * 2
        for i, part in enumerate(self.partitionsArea):
            areaFraction[i] = float(part) / totalArea

        print "Area: " + str(self.partitionsArea) + " " + str(areaFraction)


    def computePartitionPower(self):

        self.partitionsPower = [0] * 2

        for i, partition in enumerate(self.partitions):
            for cluster in partition:
                self.partitionsPower[i] += cluster.power

        totalPower = 0
        for part in self.partitionsPower:
            totalPower += part

        powerFraction = [0] * 2
        if totalPower > 0:
            for i, part in enumerate(self.partitionsPower):
                powerFraction[i] = float(part) / totalPower


        print "Power: " + str(self.partitionsPower) + " " + str(powerFraction)


    def extractPartitions(self, partitionFile):
        with open(partitionFile, 'r') as f:
            lines = f.read().splitlines()

        for i in xrange(0, 2):
            self.partitions.append(list())

        for line in lines:
            lineData = line.split()
            if lineData[2] != DUMMY_NAME:
                found, index = self.findClusterByName(lineData[2])
                partitionIndex = int(lineData[4][3]) # Fourth character of 'DieX'
                self.partitions[partitionIndex].append(self.clusters[index])


    def printPartitions(self):
        for i, partition in enumerate(self.partitions):
            print "Partition #" + str(i)
            for cluster in partition:
                print cluster.name + ", " + str(cluster.area) + ", " + str(cluster.powerDensity)


    def findHighestDensityCluster(self, clusters, unmatchableClusters):
        """
        return: - The power density of the selected cluster.
                - The ID of the cluster in the 'clusters' list.
        """
        den = 0 # highest density
        denCluster = None
        for i, cluster in enumerate(clusters):
            if cluster.powerDensity > den and \
            not elementIsInList(cluster.ID, unmatchableClusters) :
                den = cluster.powerDensity
                denCluster = i
        return denCluster, den

    def findLowDensityCluster(self, clusters, maxDensity, area):
        """
        - maxDensity is the density of the cluster that will replace the ones
            we pick here, and its power density should not be exceeded by them.
        - area is the area of the cluster to replace. The total area of the
            picked clusters here should be equal to that value.
        return: - a list of selected clusters (ID in the 'clusters' list)
        """
        clusterSelection = []
        areaSelection = 0 # total area of the selection


        # First, try to find one of the same are (+- 5 %) with a lower density
        # TODO: If several of the same area, keep the lowest density
        # for i, cluster in enumerate(clusters):
        #     isCloseEnough = closeEnough(area, cluster.area)
        #     if isCloseEnough and cluster.powerDensity < maxDensity:
        #         clusterSelection.append(i)
        #         areaSelection = cluster.area

        # If it does not work, use the accumulation of smaller clusters.
        # if len(clusterSelection) == 0:
        print "Looking for low density clusters"
        # print "areaSelection: " + str(areaSelection) + ", target area: " + str(area)
        for i, cluster in enumerate(clusters):
            # print str(cluster.powerDensity) + " " + str(cluster.area)
            if cluster.powerDensity < maxDensity and \
            closeEnough(area, areaSelection + cluster.area) and \
            not elementIsInList(i, clusterSelection):
                areaSelection += cluster.area
                clusterSelection.append(i)

        return clusterSelection, areaSelection



    def manualOverride(self):
        """
        Use the self.partitions and move clusters around.
        Choose arbitrarily the partition 0 to host the low power part.
        The objective is to move clusters with high power away from this partition,
        whilst keeping the area balanced between the partitions.
        In partition 0, pick the cluster with the highest power density. Then, in
        partition 1, take the clusters with the lowest power density with the
        same total area as the cluster from partition 0.
        At the end of each iteration, we will evaluate the quality of the solution
        on two criteria: area balance and power asymmetry. If the asymmetry
        does not reach the target (e.g. 70/30), we keep going (with a limit
        to the number of iterations).
        """

        unmatchableClusters = [] # List of cluster IDs for which lower density
                                # cluster could not be found in partition 1.

        # for i in xrange(0, 10):
        #     print "RUN #" + str(i)
        #     highDenCluster, highDen = self.findHighestDensityCluster(self.partitions[0], unmatchableClusters)
        #     highDenArea = self.partitions[0][highDenCluster].area
        #     print "High density cluster: " + str(highDen) + ", area: " + str(highDenArea)
        #     # TODO: Check if highDenCluster is not none.

        self.printPartitions()

        i = 0
        while i < len(self.partitions[0]):
            highDenCluster = i
            highDen = self.partitions[0][highDenCluster].powerDensity
            highDenArea = self.partitions[0][highDenCluster].area

            lowDenClusters, lowDenArea = self.findLowDensityCluster(self.partitions[1], highDen, highDenArea)
            if closeEnough(highDenArea, lowDenArea):
                lowDenClusters.sort()
                print "Low density clusters: (total area: " + str(lowDenArea) + ")"
                for id in lowDenClusters:
                    cluster = self.partitions[1][id]
                    print "den: " + str(cluster.powerDensity) + ", area: " + str(cluster.area)

                # Swap the clusters
                print "BEFORE SWAPING:"
                for i, part in enumerate(self.partitions):
                    print "Partition " + str(i)
                    print part
                    for c in part:
                        print c.ID

                self.partitions[1].append(self.partitions[0][highDenCluster])
                del self.partitions[0][highDenCluster]
                for id in lowDenClusters:
                    self.partitions[0].append(self.partitions[1][id])

                # Delete in reversed order because when you delete an element, the
                # others are shifted to take its place.
                for id in reversed(lowDenClusters):
                    print str(id)
                    del self.partitions[1][id]

                print "AFTER SWAPING:"
                for i, part in enumerate(self.partitions):
                    print "Partition " + str(i)
                    for c in part:
                        print c.ID

            # If the area is not close enough, the high density cluster could
            # not be matched. Blacklist its ID.
            else:
                print "High density cluster unmatchable"
                unmatchableClusters.append(self.partitions[0][highDenCluster].ID)
                i += 1

            self.computePartitionArea()
            self.computePartitionPower()
        self.printPartitions()








class Net:
    def __init__(self, name, netID):
        self.name = name
        self.ID = netID
        self.wl = 0 # wire length
        self.instances = []
        self.pins = 0 # number of pins

    def setPinAmount(self, pins):
        self.pins = pins

    def setWL(self, wl):
        self.wl = wl

    def addInstance(self, instance):
        self.instances.append(instance)

    def searchInstance(self, instance):
        found = False
        try:
            self.instances.index(instance)
        except:
            pass
        else:
            found = True
        return found


class Cluster:
    def __init__(self, name, clusterID, blackbox):
        self.name = name
        self.ID = clusterID
        self.instances = []
        self.boudndaries = [[0, 0], [0 ,0]] # [[lower X, lower U], [upper X, upper Y]] (floats)
        self.area = 0 # float
        self.weights = []   # [0] = area
                            # [1] = power
                            # [2] = area & power
        self.weightsNormalized = []
        self.connectedClusters = [] # List of Cluster IDs connected to this cluster.
        self.connectedEdges = []    # List of Hyperedge objects.
                                    # They are the edges connecting this cluster to others.
                                    # Those hyperedges are needed to establish weights.
                                    # connectedEdges[i] connects to conectedClusters[i]
        self.blackbox = blackbox    # Boolean
                                    # When a cluster is a blackbox, it's composed of only
                                    # one instance. Hence, when writting its directive into
                                    # the .tcl file, use the '-inst' modifier.
                                    # e.g. Memory are blackboxes.

        self.weights = [0] * VERTEX_WEIGHTS_TYPES
        self.weightsNormalized = [0] * VERTEX_WEIGHTS_TYPES
        self.power = 0
        self.powerDensity = 0
        self.isDummy = False


    def setBoundaries(self, lowerX, lowerY, upperX, upperY):
        self.boudndaries[0][0] = lowerX
        self.boudndaries[0][1] = lowerY
        self.boudndaries[1][0] = upperX
        self.boudndaries[1][1] = upperY

    def addInstance(self, instance):
        """
        instance: Instance object
        """
        self.instances.append(instance)

    def searchInstance(self, instance):
        # print "Searching " + instance.name + " in cluster " + self.name
        found = False
        # i = 0
        # while not found and i < len(self.instances):
        #     if self.instances[i].name == instance.name:
        #         found = True
        #     else:
        #         i += 1
        try:
            self.instances.index(instance)
        except:
            pass
        else:
            found = True
        return found

    def setArea(self, area):
        self.area = area

    def setWeight(self, index, weight):
        self.weights[index] = weight

    def setWeightNormalized(self, index, weight):
        self.weightsNormalized[index] = weight

    def searchConnectedCluster(self, cluster):
        found = False
        index = -1
        try:
            index = self.connectedClusters.index(cluster)
        except:
            pass
        else:
            found = True
        return index, found

    def setPower(self, power):
        self.power = power

    def setPowerDensity(self, powerDensity):
        self.powerDensity = powerDensity

    def setDummy(self, status):
        self.isDummy = status


class Hyperedge:
    def __init__(self):
        self.nets = [] # list of Nets
        self.clusters = [] # list of Clusters
        self.weights = []   # [0] = Number of wires
                            # [1] = Wire length
                            # [2] = 1/number of wires
                            # [3] = 1/wire length
                            # [4] = WEIGHT_COMBILI_COEF * number of wires +
                            #       (1 - WEIGHT_COMBILI_COEF) * wire length
                            # [5] = 1/[4]
        self.weightsNormalized = [] # Same weights, but normalized like so:
                                    # (weight / max_weight) * 1000

        self.weights = [0] * EDGE_WEIGHTS_TYPES
        self.weightsNormalized = [0] * EDGE_WEIGHTS_TYPES
        self.connectivity = 1 # Number of connection between the cluster inside the hyperedge.

    def addNet(self, net):
        self.nets.append(net)

    def addCluster(self, cluster):
        self.clusters.append(cluster)

    def setWeight(self, index, weight):
        self.weights[index] = weight

    def setWeightNormalized(self, index, weight):
        self.weightsNormalized[index] = weight


class Instance:
    def __init__(self, name):
        self.name = name

# def initWeightsStr(mydir, metisInputFiles, paritionFiles, partitionDirectivesFiles):
def initWeightsStr(edgeWeightTypesStr, vertexWeightTypesStr):
    '''
    Gives a name to the the different kind of edge weights adn vertex weights.
    '''

    # TODO sub-optimial loop. Why did I use all those if?
    for edgeWeightType in xrange(0, EDGE_WEIGHTS_TYPES):
        if edgeWeightType == 0:
            edgeWeightTypesStr.append("01_NoWires")
        if edgeWeightType == 1:
            edgeWeightTypesStr.append("02_1-NoWires")
        if edgeWeightType == 2:
            edgeWeightTypesStr.append("03_TotLength")
        if edgeWeightType == 3:
            edgeWeightTypesStr.append("04_1-TotLength")
        if edgeWeightType == 4:
            edgeWeightTypesStr.append("05_AvgLength")
        if edgeWeightType == 5:
            edgeWeightTypesStr.append("06_1-AvgLength")
        if edgeWeightType == 6:
            edgeWeightTypesStr.append("07_NoWiresXTotLength")
        if edgeWeightType == 7:
            edgeWeightTypesStr.append("08_1-NoWiresXTotLength")
        if edgeWeightType == 8:
            edgeWeightTypesStr.append("09_NoWires+TotLength")
        if edgeWeightType == 9:
            edgeWeightTypesStr.append("10_1-NoWires+TotLength")

    if SIMPLE_GRAPH and VERTEX_WEIGHTS_TYPES == 2:
        vertexWeightTypesStr.append("area-power")
    else:
        for vertexWeightType in xrange(0, VERTEX_WEIGHTS_TYPES):
            if vertexWeightType == 0:
                vertexWeightTypesStr.append("area")
            elif vertexWeightType == 1:
                vertexWeightTypesStr.append("power")



#----------------------------------------------------------------
#----------------------------------------------------------------
#----------------------------------------------------------------
if __name__ == "__main__":
#==========================================================================
# Read rpt gen with report physical.connectivity -net_threshold 0
#------------------------------------------------------------------------------------------------------------------------------------------------
#SourceBlock | SourceType | SourceBlockArea | ConnectedBlock | ConnectedType | ConnectedBlockArea | E1->E2 | E2->E1 | E1-E2 | Total Connections
#------------------------------------------------------------------------------------------------------------------------------------------------
#   connectivity = RPTFile("4rpt.phys_conn.rpt", 34, 2)
#   connectivity.Read()
#==========================================================================
# Read rpt gen with report physical.hierarchy
#    --------------------------------------------
#    Name | Type | Area | Inst | Cnt |  Area(%)
#    --------------------------------------------
    # dirs=["../input_files/"]
    # dirs=["../ccx/"]
    # dirs=["../CCX_HL1/"]
    # dirs=["../CCX_HL2/"]
    # dirs=["../CCX_HL3/"]
    # dirs=["../CCX_HL4/"]
    dirs = ["../MPSoC/"]
    # dirs = ["../spc_L3/"]
    # dirs = ["../spc_HL1/"]
    # dirs = ["../spc_HL2/"]
    # dirs = ["../SPC/spc_HL3/"]
    # dirs = ["../SPC/spc_HL2/"]
    # dirs = ["../CCX_Auto0500/"]
    # dirs = ["../CCX_Auto1000/"]
    # dirs = ["../RTX/RTX_HL3/"]
    # dirs = ["../RTX/RTX_HL2/"]
    # dirs = ["../RTX/RTX_A0500/"]
    # dirs = ["../RTX/RTX_A1000/"]

    # Random seed is preset or random, depends on weither you want the same results or not.
    # Note: even if the seed is set, maybe it won't be enough to reproduce the results since the partitioner may use its own.
    if RANDOM_SEED == 0:
        RANDOM_SEED = random.random()
    random.seed(RANDOM_SEED)
    print "Seed: " + str(RANDOM_SEED)

    # Initialize lists to be used later.
    edgeWeightTypesStr = list()
    vertexWeightTypesStr = list()
    initWeightsStr(edgeWeightTypesStr, vertexWeightTypesStr)

    graph = Graph()
    clusterCount = 500 # Ken's cluster count. Used if CLUSTER_INPUT_TYPE == 1

    for mydir in dirs:

        if not IMPORT_HYPERGRAPH:
            if CLUSTER_INPUT_TYPE == 0:
                clustersAreaFile = mydir + "ClustersArea.out"
                clustersInstancesFile = mydir + "ClustersInstances.out"
            elif CLUSTER_INPUT_TYPE == 1:
                clustersAreaFile = mydir + "test" + str(clusterCount) + ".area"
                clustersInstancesFile = mydir + "test" + str(clusterCount) + ".tcl"
            elif CLUSTER_INPUT_TYPE == 2:
                clustersAreaFile = mydir + "2rpt.clusters.rpt"
                clustersInstancesFile = mydir + "ClustersInstances.out"

            netsInstances = mydir + "InstancesPerNet.out"
            netsWL = mydir + "WLnets.out"
            memoryBlocksFile = mydir + "bb.out"
            # memoryBlocksFile = mydir + "1.bb.rpt"

            # Extract clusters
            if CLUSTER_INPUT_TYPE == 0:
                graph.ReadClusters(clustersAreaFile, 14, 2)
            elif CLUSTER_INPUT_TYPE == 1:
                graph.ReadClusters(clustersAreaFile, 0, 0)


            # Extract cluster instances
            t0 = time.time()
            graph.readClustersInstances(clustersInstancesFile, 0, 0)
            t1 = time.time()
            print "time: " + str(t1-t0)
            if MEMORY_BLOCKS:
                t0 = time.time()
                graph.readMemoryBlocks(memoryBlocksFile, 14, 4)
                t1 = time.time()
                print "time: " + str(t1-t0)
            # Begin with the netWL file, as there are less nets there.
            graph.readNetsWireLength(netsWL, 14, 2)
            graph.readNets(netsInstances, 0, 0)

            t0 = time.time()
            graph.findHyperedges()
            t1 = time.time()
            print "time: " + str(t1-t0)

            print "Dumping the graph into " + mydir + DUMP_FILE
            with open(mydir + DUMP_FILE, 'wb') as f:
                pickle.dump(graph, f)

        else:
            print "Loading the graph from " + mydir + DUMP_FILE
            with open(mydir + DUMP_FILE, 'rb') as f:
                graph = pickle.load(f)

        edgeWeightType = 0
        graph.computeClustersPower()
        graph.computeHyperedgeWeights(True)
        graph.computeVertexWeights()

        paritionFiles = []

        for edgeWeightType in xrange(0, len(edgeWeightTypesStr)):
            for vertexWeightType in xrange(0, len(vertexWeightTypesStr)):
                if ALGO == 0: # METIS
                    metisInput = mydir + "metis_" + edgeWeightTypesStr[edgeWeightType] + \
                        "_" + vertexWeightTypesStr[vertexWeightType] + ".hgr"
                    metisPartitionFile = metisInput + ".part.2"
                    partitionDirectivesFile = metisInput + ".tcl"

                    print "============================================================="
                    print "> Edge weight: " + edgeWeightTypesStr[edgeWeightType]
                    print "> Vertex weight: " + vertexWeightTypesStr[vertexWeightType]
                    print "============================================================="

                    graph.generateMetisInput(metisInput, edgeWeightType, vertexWeightType)
                    graph.GraphPartition(metisInput)
                    graph.WritePartitionDirectives(metisPartitionFile, partitionDirectivesFile)
                    graph.extractPartitions(partitionDirectivesFile)
                    graph.computePartitionArea()
                    graph.computePartitionPower()
                    if MANUAL_ASYMMETRY:
                        graph.manualOverride()
                    paritionFiles.append(metisPartitionFile)

                elif ALGO == 1: # PaToH
                    patohInput = mydir + "patoh_" + edgeWeightTypesStr[edgeWeightType] + \
                        "_" + vertexWeightTypesStr[vertexWeightType] + ".hgr"
                    patohPartitionFile = patohInput + ".part.2"
                    partitionDirectivesFile = patohInput + ".tcl"

                    print "=======================PaToH================================="
                    print "> Edge weight: " + edgeWeightTypesStr[edgeWeightType]
                    print "> Vertex weight: " + vertexWeightTypesStr[vertexWeightType]
                    print "============================================================="

                    graph.generatePaToHInput(patohInput, edgeWeightType, vertexWeightType)
                    graph.GraphPartitionPaToH(patohInput)
                    graph.WritePartitionDirectives(patohPartitionFile, partitionDirectivesFile)
                    graph.extractPartitions(partitionDirectivesFile)
                    graph.computePartitionArea()
                    graph.computePartitionPower()


        graph.hammingReport(paritionFiles)
        # graph.plotWeights()
