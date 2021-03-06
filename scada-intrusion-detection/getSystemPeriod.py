import os
import warnings
import sys
from readData import *
from scipy.fftpack import fft
from scipy.signal import blackman
import matplotlib.pyplot as plt
import numpy as np
from operator import itemgetter 
from sklearn import mixture
from operator import truediv
from hmmlearn import hmm
#from sklearn import hmm
from statistics import mean
from statistics import stdev
import math
from sklearn.decomposition import PCA
from autoperiod import *
from statsmodels import tsa
from statsmodels.tsa import stattools
import statsmodels
warnings.simplefilter("ignore", DeprecationWarning)



nMaxPeriods = 0
maxMixtures = 1
windowSize = 60
testPCA = True


argList = sys.argv
scriptDir = os.path.dirname(os.path.realpath(__file__))



def extractAverageSamplingPeriod(trainSamples):
	N = len(trainSamples)
	i = 1
	T = 0.0
	nFields = len(trainSamples[0])
	while i < N :
		T = T + float(trainSamples[i][nFields-1]) - float(trainSamples[i-1][nFields-1])
		i = i + 1

	T = T/float(N*1000)
	return T

def getStateSimilarityMatrix(observations,nStages,nMixtures) :

	Sim = []
	j = 0
	while j < 2*nStages :
		currStateSim = []
		i = 0
		while i < 2*nStages :
			if j < nStages:
				srcStateGMM = observations[j]['gmms'][nMixtures - 1]
				if i < nStages :
					dstStateSamples = observations[i]['samples']
				elif len(observations[i % nStages]['anomalousSamples']) > 0 :
					dstStateSamples = observations[i % nStages]['anomalousSamples']
				if dstStateSamples != None :
					currStateSim.append(srcStateGMM.bic(np.array(dstStateSamples)))
					dstStateSamples = None
			elif len(observations[j % nStages]['anomalousSamples']) > 0 :
				srcStateGMM = observations[j % nStages]['agmms'][nMixtures - 1]
				if i < nStages :
					dstStateSamples = observations[i]['samples']
				elif len(observations[i % nStages]['anomalousSamples']) > 0 :
					dstStateSamples = observations[i % nStages]['anomalousSamples']
				if dstStateSamples != None :
					currStateSim.append(srcStateGMM.bic(np.array(dstStateSamples)))
					dstStateSamples = None
			i = i + 1

		Sim.append(currStateSim)
		j = j + 1
		
	print "BIC State Similarity Matrix (Lower values => more Similar) = "
	print np.array(Sim)
	return Sim
				
				

def getFFT(signal,T):

	N = len(signal)
	xf = np.linspace(0.0, 1.0/(2.0*float(T)), N/2)
	w = blackman(N)
	ffts = []
	sfft = fft(np.array(signal)*w)

	return xf,sfft
	
	

def plotSignal(signal,N=100):


	x = np.linspace(0,N,N)
	plt.plot(x,signal[0:N])
	plt.grid()
	plt.show()

def scoreSamples(samples,hmm,windowSize) :
	scores = []
	assert windowSize > 0
	N = windowSize
	nWindows = int(len(samples)/windowSize)
	nSamples = len(samples)
	i = 0
	while i + N < nSamples :
		scores.append(hmm.score(np.array(samples[i:i+N])))
		#i = i  + 1
		i = i + N
		
	scores.append(hmm.score(np.array(samples[i:])))
	if len(scores) > 1 :
		return mean(scores)/float(windowSize),(1.96*stdev(scores))/float(math.sqrt(len(scores)))
	else :
		return mean(scores)/float(windowSize),0.0
	

def trainHMM(observations,trainSamples,nMixtures=1,nStages=1,cvType='diag') :

	nStates = nStages
	assert nStates > 0
	transmat = []
	startProb = [float(1.0/nStates)]*nStates
	startProb = [0.0]*nStates
	startProb[0] = 1.0
	
	for j in xrange(0,nStates) :
		transmat.append([0.0]*nStates)
		transmat[j][j] = 1


	
	
	transmat = np.array(transmat)
	means = []
	covars = []
	weights = []
	gmms = []

	for j in xrange(0,nStages) :
		if j < nStages :
			gmm = observations[j]['gmms'][nMixtures - 1]
		
		if gmm != None :	
			means.append(gmm.means_)
			covars.append(gmm.covars_)
			weights.append(gmm.weights_)
			gmms.append(gmm)
			gmm = None


		

	means = np.array(means)
	covars = np.array(covars)
	weights = np.array(weights)
	
	
	

	if nStates >= nStages :
		gmmHMM = hmm.GMMHMM(n_components=nStates,n_mix=nMixtures,covariance_type=cvType,params='', init_params='',n_iter=10000,tol=0.0001)
		#gmmHMM = hmm.GaussianHMM(n_components=nStates,n_iter=10000,tol=0.0001,params='',covariance_type=cvType,init_params='')
		gmmHMM.means_ = means
		gmmHMM.covars_ = covars
		gmmHMM.weights_ = weights

		gmmHMM.startprob_ = np.array(startProb)
		gmmHMM.transmat_  = np.array(transmat)
		gmmHMM.gmms_ = gmms
		#gmmHMM.fit(np.array(trainSamples))
		
		print "GMMHMM Score = ", gmmHMM.score(np.array(trainSamples))
		
		
		

	return gmmHMM
	


def trainGMMs(trainSamples,sysPeriod=1,nMaxMixtures=10,cvType='full') :
	assert len(trainSamples) > 0
	nFeatures = len(trainSamples[0])
	nSamples = len(trainSamples)
	nStages = sysPeriod
	observations = {}
	featureMax = []

	for i in xrange(0,nStages):
		observations[i] = {}
		observations[i]['samples'] = []
		observations[i]['gmms'] = []
		observations[i]['bic'] = []


	for i in xrange(0,nSamples):
		currStage = i % nStages
		observations[currStage]['samples'].append(trainSamples[i])


	max_BIC_List = []
	for i in xrange(1,nMaxMixtures+1):
		max_BIC = -np.infty
		for j in xrange(0,nStages) :
			g = mixture.GMM(n_components=i,covariance_type=cvType,n_iter=100000,tol=0.0001)
			g.fit(np.array(observations[j]['samples']))
			bic = float(g.bic(np.array(observations[j]['samples'])))
			observations[j]['bic'].append(bic)
			observations[j]['gmms'].append(g)
			
			if bic > max_BIC :
				max_BIC = bic
		max_BIC_List.append(max_BIC)

	
	
	nOptMixtures = max_BIC_List.index(min(max_BIC_List)) + 1
	
	#print "Max BICs For Samples w.r.t nMixtures = ", max_BIC_List
	#print "Optimum number of Mixtures = ", nOptMixtures, " min_max_BIC_list = ", max_BIC_List

	assert nOptMixtures <= nMaxMixtures
	return observations, nOptMixtures
		
def plotInterestingFFTs(trainCharacteristics) :
	plt.close('all')
	plt.subplots_adjust(hspace=0.7)
	N= len(trainCharacteristics['FunctionCode'][3])

	xf,fCode3 = getFFT(normalize(trainCharacteristics['FunctionCode'][3], [max(trainCharacteristics['FunctionCode'][3])]),1)
	xf,fCode16 = getFFT(normalize(trainCharacteristics['FunctionCode'][16],[max(trainCharacteristics['FunctionCode'][16])]),1)
	xf,networkBytes = getFFT(normalize(trainCharacteristics['Network']['Bytes'],[max(trainCharacteristics['Network']['Bytes'])]),1)
	xf,setpoint = getFFT(normalize(trainCharacteristics['Registers'][16]['w'],[max(trainCharacteristics['Registers'][16]['w'])]),1)	
	xf,pipelinePSI = getFFT(normalize(trainCharacteristics['Registers'][14]['r'],[max(trainCharacteristics['Registers'][14]['r'])]),1)	

	
	f,axarr = plt.subplots(3,2)
	#plt.semilogy(xf,fCode3)
	#axarr[0,0].semilogy(xf[1:N/2], 2.0/N * np.abs(fCode3[1:N/2] + 1), '-r')
	axarr[0,0].set_ylim(0,max(2.0/N * np.abs(fCode3[1:N/2])))
	axarr[0,0].set_xlim([-0.05,0.5])
	axarr[0,0].plot(xf[1:N/2], 2.0/N * np.abs(fCode3[1:N/2]), '-r')
	axarr[0,0].set_title("FFT - Function Code 3 Access")
	axarr[0,0].grid(True)

	
	#plt.semilogy(xf,fCode16)
	#axarr[0,1].semilogy(xf[1:N/2], 2.0/N * np.abs(fCode16[1:N/2] + 1), '-r')
	axarr[0,1].set_ylim(0,max(2.0/N * np.abs(fCode16[1:N/2])))
	axarr[0,1].set_xlim([-0.05,0.5])
	axarr[0,1].plot(xf[1:N/2], 2.0/N * np.abs(fCode16[1:N/2]), '-r')
	axarr[0,1].set_title("FFT - Function Code 16 Access")
	axarr[0,1].grid(True)

	
	#plt.semilogy(xf,setpoint)
	#axarr[1,0].semilogy(xf[1:N/2], 2.0/N * np.abs(setpoint[1:N/2] + 1), '-r')
	axarr[1,0].set_ylim(0,max(2.0/N * np.abs(setpoint[1:N/2])))
	axarr[1,0].set_xlim([-0.05,0.5])
	axarr[1,0].plot(xf[1:N/2], 2.0/N * np.abs(setpoint[1:N/2]), '-r')
	axarr[1,0].set_title("FFT - Setpoint Reg Write")
	axarr[1,0].grid(True)


	#plt.semilogy(xf,pipelinePSI)
	#axarr[1,1].semilogy(xf[1:N/2], 2.0/N * np.abs(pipelinePSI[1:N/2] + 1), '-r')
	axarr[1,1].set_ylim(0,max(2.0/N * np.abs(pipelinePSI[1:N/2])))
	axarr[1,1].set_xlim([-0.05,0.5])
	axarr[1,1].plot(xf[1:N/2], 2.0/N * np.abs(pipelinePSI[1:N/2]), '-r')
	axarr[1,1].set_title("FFT - Pressure Reg Read")
	axarr[1,1].grid(True)

	
	#plt.semilogy(xf,networkBytes)
	#axarr[2,0].semilogy(xf[1:N/2], 2.0/N * np.abs(networkBytes[1:N/2] + 1), '-r')
	axarr[2,0].set_ylim(0,max(2.0/N * np.abs(networkBytes[1:N/2])))
	axarr[2,0].set_xlim([-0.05,0.5])
	axarr[2,0].plot(xf[1:N/2], 2.0/N * np.abs(networkBytes[1:N/2]), '-r')
	axarr[2,0].set_title("FFT - Network Bytes")
	axarr[2,0].grid(True)

	axarr[2,1].axis('off')


	plt.tight_layout()
	plt.show()

def plotPCAFFTs(trainSamples) :

	nSamples = len(trainSamples)
	assert nSamples > 1
	nSignals = len(trainSamples[0])
	if nSignals >= 12 :
		nSignals = 12
	assert nSignals >= 1 

	if nSignals <= 2 :
		f,axarr = plt.subplots(2)
	else :		
		f,axarr = plt.subplots(int(nSignals/2) + nSignals % 2,2)

	N = nSamples
	for i in xrange(0,nSignals):

		subplotX = int(i/2)
		subplotY = i % 2
		signal = np.array(map(itemgetter(i),trainSamples))

		xf,fftVal = getFFT(signal,1)
		if nSignals <= 2 :
			axarr[subplotY].plot(xf[1:N/2], 2.0/N * np.abs(fftVal[1:N/2]), '-r')
			axarr[subplotY].set_title("FFT - Signal No : " + str(i + 1))
			axarr[subplotY].grid(True)
		else :
			axarr[subplotX,subplotY].plot(xf[1:N/2], 2.0/N * np.abs(fftVal[1:N/2]), '-r')
			axarr[subplotX,subplotY].set_title("FFT - Signal No : " + str(i + 1))
			axarr[subplotX,subplotY].grid(True)


	plt.tight_layout()
	plt.show()
		


	
	

def extractOptPCADimensionality(trainSamples) :
	assert len(trainSamples) >= 2 
	nFeatures = len(trainSamples[0])
	pca = PCA(n_components=nFeatures)
	pca.fit(trainSamples)

	percentageExplainedVariance = []
	nComponents = []
	pSum  = 0.0
	nComponents99 = -1

	for i in xrange(0,nFeatures) :
		pSum = pSum + pca.explained_variance_ratio_[i]
		if pSum >= 0.99 and nComponents99 == -1 :
			nComponents99 = i + 1
		nComponents.append(i+1)
		percentageExplainedVariance.append(pSum*100.0)


	#plt.plot(nComponents,percentageExplainedVariance)
	#plt.title("Percentage of Explained Variance vs number of Dimensions (in PCA)")
	#plt.ylabel("Explained Variance (%)")
	#plt.xlabel("n Dimensions")
	#plt.xticks(np.arange(0, nFeatures + 1, 1.0))
	#plt.grid(True)
	#plt.show()

	assert nComponents99 != -1
	return nComponents99

def normalize(timeSeries,nfFactor) :

	if isinstance(timeSeries[0],(int,float)) == True :
		nFeatures = 1
	else :
		nFeatures = len(timeSeries[0])

	assert len(nfFactor) == nFeatures
	nSamples = len(timeSeries)
	normalizedTimeSeries = []

	for i in xrange(0,nFeatures) :
		if nfFactor[i] == 0.0 :
			nfFactor[i] = 1.0

	for i in xrange(0,nSamples):
		if isinstance(timeSeries[0],(int,float)) == True :
			normalizedTimeSeries.append(float(timeSeries[i])/float(nfFactor[0]))
		else :
			normalizedTimeSeries.append(map(truediv,timeSeries[i],nfFactor))


	return np.array(normalizedTimeSeries)


def standardize(timeSeries,musigmaEstimates=None) :

	if musigmaEstimates == None :
		toEstimate = True
	else :
		toEstimate = False



	nSamples = len(timeSeries)
	assert nSamples >= 2
	


	if isinstance(timeSeries[0],(int,float)) == True :
		nFeatures = 1
		if toEstimate == True :
			mu = mean(timeSeries)
			sigma = stdev(timeSeries)
		else :
			mu = musigmaEstimates[0]
			sigma = musigmaEstimates[1]
	else :
		nFeatures = len(timeSeries[0])
		if toEstimate == True :
			mu = []
			sigma = []
			for i in xrange(0,nFeatures) :
				signal = np.array(map(itemgetter(i),timeSeries))
				mu.append(mean(signal))
				sigma.append(stdev(signal))
		else :
			mu = musigmaEstimates[0]
			sigma = musigmaEstimates[1]


	assert mu != None
	assert sigma != None

	standardizedTimeSeries = []

	for i in xrange(0,nSamples):
		if isinstance(timeSeries[0],(int,float)) == True :
			if sigma == 0.0 :
				print "The only signal available is a constant. Any variation can be detected as anomaly. Exiting."
				sys.exit(0)
			else :
				standardizedTimeSeries.append(float(timeSeries[i] - float(mu))/float(sigma))

		else :
			standardizedInput = []
			nNonConstants = 0

			for j in xrange(0,nFeatures):
				if sigma[j] != 0.0 :
					standardizedInput.append(float(timeSeries[i][j] - float(mu[j]))/float(sigma[j]))
					nNonConstants = nNonConstants + 1
				else :
					standardizedInput.append(float(timeSeries[i][j] - 0.0)/float(1.0))
		
			if nNonConstants == 0 :
				print "All available signals available are constant. Any variation can be detected as anomaly. Exiting."
				sys.exit(0)
			else :
				standardizedTimeSeries.append(standardizedInput)


	return np.array(standardizedTimeSeries),(mu,sigma)
				
	


	

	

if __name__ == "__main__" :


	trainCommandFile = scriptDir + '/DataSets/Command_Injection/AddressScanScrubbedV2.csv'
	trainResponseFile = scriptDir + '/DataSets/Response_Injection/ScrubbedBurstV2/scrubbedBurstV2.csv'
	dosAttackDataFile = scriptDir + '/DataSets/DoS_Data_FeatureSet/modbusRTU_DoSResponseInjectionV2.csv'
	functionScanDataFile = scriptDir + '/DataSets/Command_Injection/FunctionCodeScanScrubbedV2.csv'
	burstResponseFile = scriptDir + '/DataSets/Response_Injection/ScrubbedBurstV2/scrubbedBurstV2.csv'
	fastburstResponseFile = scriptDir + '/DataSets/Response_Injection/ScrubbedFastV2/scrubbedFastV2.csv'
	slowburstResponseFile = scriptDir + '/DataSets/Response_Injection/ScrubbedSlowV2/scrubbedSlowV2.csv'
	
	np.random.seed(123456)
	assert os.path.isfile(trainCommandFile)
	assert os.path.isfile(trainResponseFile)
	assert os.path.isfile(dosAttackDataFile)
	assert os.path.isfile(functionScanDataFile)
	assert os.path.isfile(burstResponseFile)
	assert os.path.isfile(fastburstResponseFile)
	assert os.path.isfile(slowburstResponseFile)
	
	print "Reading Train and Test Samples ..."
	traincharacteristics,timeSeries = readTrainSamplesNetworkData(trainCommandFile,trainResponseFile,1,1000,28071)
	print "Reading DoS Data ..."	
	characteristics,dosAttackData = readTestSamplesNetworkData(dosAttackDataFile,28072,1000)
	print "Reading Function Code Scan Data ..."
	characteristics,functionScanData = readTestSamplesNetworkData(functionScanDataFile,28088,1000)
	print "Reading burst response .."
	characteristics,burstResponseData = readTestSamplesNetworkData(burstResponseFile,28072,1000)
	print "Reading fast burst ..."
	characteristics,fastburstResponseData = readTestSamplesNetworkData(fastburstResponseFile,28072,1000)
	print "Reading slow burst ..."
	characteristics,slowburstResponseData = readTestSamplesNetworkData(slowburstResponseFile,28072,1000)


	#extract maximum feature values from train Samples for normalization
	nSamples = len(timeSeries)

	"""
	timeSeries = []
	i = 0
	while i < nSamples :
		timeSeries.append([np.sin(0.1*2.0*np.pi*i),np.cos(0.2*2.0*np.pi*i)])
		i = i + 1
	
	timeSeries = np.array(timeSeries)
	"""
	

	"""
	#standardize all samples
	print "Standardizing samples ..."


	timeSeries,musigma = standardize(timeSeries)
	dosAttackData,tmp = standardize(dosAttackData,musigma)
	functionScanData,tmp = standardize(functionScanData,musigma)
	burstResponseData,tmp = standardize(burstResponseData,musigma)
	fastburstResponseData,tmp = standardize(fastburstResponseData,musigma)
	slowburstResponseData,tmp = standardize(slowburstResponseData,musigma)
	"""

	print "nSamples = ", nSamples, " n Signals = ", len(timeSeries[0])
	print "Normalizing samples ..."
	nFeatures = len(timeSeries[0])
	featureMax = []
	i = 0	
	while i < nFeatures :
		maxVal = max(np.array(map(itemgetter(i), timeSeries)),key=abs) 
		if maxVal == 0:
			maxVal = 1
		featureMax.append(maxVal)
		i = i + 1
	
	timeSeries = normalize(timeSeries,featureMax)
	dosAttackData = normalize(dosAttackData,featureMax)
	functionScanData = normalize(functionScanData,featureMax)
	burstResponseData = normalize(burstResponseData,featureMax)
	fastburstResponseData = normalize(fastburstResponseData,featureMax)
	slowburstResponseData = normalize(slowburstResponseData,featureMax)	

	
	#dimensionality Reduction with PCA
	if testPCA == True :

		optDimensionality = extractOptPCADimensionality(timeSeries)
		print "PCA 99 percentile optDimensionality = ", optDimensionality
		pca = PCA(n_components=optDimensionality)
		pca.fit(timeSeries)
		timeSeries = pca.transform(timeSeries)
		dosAttackData = pca.transform(dosAttackData)
		functionScanData = pca.transform(functionScanData)
		burstResponseData = pca.transform(burstResponseData)
		fastburstResponseData = pca.transform(fastburstResponseData)
		slowburstResponseData = pca.transform(slowburstResponseData)


	nSignals = len(timeSeries[0])
	nSignals = 1
	nLags = 50
	for i in xrange(0,nSignals) :
		print "Extracting candidate periods for signal ", i, " ..."
		candidatePeriods,pThreshold = getPeriodHints(X=np.array(map(itemgetter(i),timeSeries)),fs=1.0)
		print "Candidate Periods = ", candidatePeriods
		print "pThreshold = ",pThreshold

		print "Estimating Acf for signal ", i , " ..."
		#acf = statsmodels.tsa.stattools.acf(x=np.array(map(itemgetter(i),timeSeries)),nlags=nLags,fft=True)
		acf = stattools.acf(x=np.array(map(itemgetter(i),timeSeries)),nlags=nLags,fft=True)

		plt.plot(acf)
		plt.title("ACF for Signal " + str(i))
		plt.xlabel("Lags")
		plt.ylabel("Auto Correlation")
		plt.xticks(np.arange(0, nLags + 5 , int(nLags/20)))
		plt.show()
	


	#for i in xrange(0,len(timeSeries[0])) :
	#	print "new mu[",i,"] = ", mean(np.array(map(itemgetter(i),timeSeries)))
	#	print "new sigma[",i,"] = ", stdev(np.array(map(itemgetter(i),timeSeries)))
	

	#plotPCAFFTs(timeSeries)
	#plotSignal(np.array(map(itemgetter(0),timeSeries)),5*windowSize)
	#plotSignal(np.array(map(itemgetter(1),timeSeries)),5*windowSize)
	#plotSignal(np.array(map(itemgetter(2),timeSeries)),5*windowSize)
	#plotSignal(np.array(map(itemgetter(3),timeSeries)),5*windowSize)
	#plotSignal(np.array(map(itemgetter(4),timeSeries)),5*windowSize)

	#sys.exit(0)
	#plotInterestingFFTs(traincharacteristics)
	#sys.exit(0)


	trainMeans = []
	trainErrs = []
	doSMeans = []
	doSErrs = []
	fScanMeans = []
	fScanErrs = []
	bRMeans = []
	bRErrs = []
	fbRMeans = []
	fbRErrs = []
	sbRMeans = []
	sbRErrs = []

	
	start = 1
	period = []
	while start < nMaxPeriods + 1:
		sysPeriod = start
		period.append(sysPeriod)
		print "Training HMM for SysPeriod = ",sysPeriod

		if testPCA == False :
			covType = 'full'
		else :
			covType = 'diag' # pca decorrelates signals

		observations, nOptMixtures = trainGMMs(timeSeries,sysPeriod=sysPeriod,nMaxMixtures=maxMixtures,cvType=covType)
		Hmm = trainHMM(observations=observations,trainSamples=timeSeries,nMixtures=nOptMixtures,nStages=sysPeriod,cvType=covType)
				
		windowSize = sysPeriod
		print "Scoring Samples ..."
		mu,err = scoreSamples(timeSeries,Hmm,windowSize)
		trainMeans.append(mu)
		trainErrs.append(err)
	
		#print "BIC HMM = ", -2*Hmm.score(np.array(timeSeries)) + sysPeriod*(math.log(nSamples))
		mu,err = scoreSamples(dosAttackData,Hmm,windowSize)
		doSMeans.append(mu)
		doSErrs.append(err)
		mu,err = scoreSamples(functionScanData,Hmm,windowSize)
		fScanMeans.append(mu)
		fScanErrs.append(err)
		mu,err = scoreSamples(burstResponseData,Hmm,windowSize)
		bRMeans.append(mu)
		bRErrs.append(err)
		mu,err = scoreSamples(fastburstResponseData,Hmm,windowSize)
		fbRMeans.append(mu)
		fbRErrs.append(err)
		mu,err = scoreSamples(slowburstResponseData,Hmm,windowSize)
		sbRMeans.append(mu)
		sbRErrs.append(err)
		

		start =  start + 1
		
	

	if nMaxPeriods > 1 :
		trainLine = plt.errorbar(period,trainMeans,yerr=trainErrs,label="Train Samples",linestyle='--',marker="d",color="red")

		"""	
		doSLine = plt.errorbar(period,doSMeans,yerr=doSErrs,label="DoS Attack",linestyle='-',marker="+",color="black")
		fScanLine = plt.errorbar(period,fScanMeans,yerr=fScanErrs,label="Function Scan",linestyle='-.',marker="^",color="green")
		bRLine = plt.errorbar(period,bRMeans,yerr=bRErrs,label="Burst Response",linestyle='-',marker="x", color="blue")
		fbRLine = plt.errorbar(period,fbRMeans,yerr=fbRErrs,label="Fast Burst",linestyle='--',marker='*',color="m")
		sbRLine = plt.errorbar(period,sbRMeans,yerr=sbRErrs,label="Slow Burst",linestyle='-',marker='o',color="green")
		plt.yscale('symlog')
		"""

		plt.title("Log Likelihood Variation for Window Size = 60 sec")
		plt.xlabel("Number of States")
		plt.ylabel("HMM average log likelihood")
		plt.xticks(np.arange(min(period), max(period) + 5 , 1.0))
		
		plt.legend(loc='upper right',shadow=True)
		plt.grid(True)
		plt.show()
	

	
