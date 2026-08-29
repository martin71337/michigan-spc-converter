Running NCAT from the Command Line.
________________________________________________________
No internet connectivity is needed to run NCAT from the command line.
This version does not support datum transformations. For state plane coordinates,only SPCS2022 is supported.
Conversions between legacy SPC zones and SPCS2022 are not currently supported. All coordinates are assumed to be in modern reference frames.

To run NCAT from the command line:
Navigate to the directory where the downloaded application is unzipped
Run the command using a format that meets your requirement(see formats and examples below). 

Results are generated in JSON format which may be directed to a text file.
Commands may be embedded in a script or program as needed.

Reference Frames Supported : N/P/C/MATREF
_______________________________________________________________________________________


Format of latitude and longitude
________________________________
Latitude and longitude may be entered in decimal degrees, 
Degrees-Minutes-Seconds(DMS), or mixed mode.
If a DMS format is used:
	Prefix the value with a hemisphere designator (N or S for latitudes and E or W for longitudes),
	and use
 	DDMMSS.ssssss format for latitudes and
	DDDMMSS.ssssss format for longitudes
	Decimal seconds are optional, up to 6 decimals may be used.

For decimal degrees, negative west longitude convention is used.

Where applicable, if no ellipsoid height is used, ellipsoid height input should be set to N/A;
if no orthometric height is used, orthometric height input should be set to N/A.

A description of keywords used in formats is as follows.

Keyword		Description
_________       _____________________________________________________________________________________
<lat>       	Latitude (in decimal degrees or DMS)
<lon>       	Longitude (in decimal degrees or DMS)
<h>       	Ellipsoid height. Use the keyword N/A, if no ellipsoid height is available.	    	
<H>             Orthometric height 
<heightUnits>   Units of Ellipsoid or Orthometric height(m,usft,or ift); an optional parameter. 
                If not specified,units default to meters.               
<inDatum>   	Input reference frame (a valid input reference frame or N/A)
<outDatum>  	Set it to br the same as input datum. No transformation supported.
<inVertDatum>   Input geopotential Datum (a valid input geopotential datum or N/A)
<outVertDatum>  Set it to br the same as input datum. No transformation supported.
<spcZone>   	A 6-digit SPC zone
<utmZone>   	A 2-digit UTM zone; For UTM conversion, utmzone is a required field. For other conversions,
		UTM zone is automatically determined when the keyword "auto" used. You may optionally 
		override this by specifying your own 2-digit UTM zone
<destZone>  	An optional 6-digit SPC zone or 2-digit UTM zone used to convert SPC or UTM coordinate
	 	from one zone to the other
<northing>  	Northing 
<easting>   	Easting  
<units>     	Units of northing and easting (m or ift); needed only for SPC conversions 
<hemi>      	Hemisphere for UTM conversion (N or S); needed only for UTM conversions 
<usng>      	USNG at 1-meter resolution
<x>         	X-coordinate in meters
<y>         	Y-coordinate in meters
<z>         	Z-coordinate in meters
<radius>    	Equatorial radius in meters
<invf>      	Inverse of flattening

llh         	lat-lon-ellipsoid height is being used for input, case sensitive
llH         	lat-lon-orthometric height is being used for input, case sensitive
spch         	SPC-ellipsoid coordinate is being used for input, case sensitive
spcH         	SPC-orthometric coordinate is being used for input, case sensitive
utmh         	UTM-ellipsoid height coordinate is being used for input, case sensitive
utmH         	UTM-orthometric height coordinate is being used for input, case sensitive
usngh        	USNG-ellipsoid height coordinate is being used for input, case sensitive
usngH        	USNG-orthometric height coordinate is being used for input, case sensitive
XYZ         	XYZ coordinate is being used for input, case sensitive

-Dparms     	A keyword used on the command line to provide input data
-Dgpath     	A keyword used to specify the path of grids directory

Conversions
________________________________________

When reference frames or datums chosen for input and output are the same, no transformation
takes place. No grids are needed for this option.

Command line formats and examples:
         

Format#1 (lat-long-ellipsoid height conversion):
java -Dparms=llh,<lat>,<lon>,<h>,<inDatum>,<outDatum><spcZone><utmZone><heightUnits> -jar jtransform_thin.jar

example#1:
java -Dparms=llh,40.0,-80.0,100.0,NAD83(1986),NAD83(1986),3702,auto -jar jtransform_thin.jar
(height units not specified;defaults to meters)
java -Dparms=llh,40.0,-80.0,100.0,NAD83(1986),NAD83(1986),3702,auto,ift -jar jtransform_thin.jar
(height units specified)

Format#1a (lat-long-ellipsoid height conversion for an international coordinate)
java -Dparms=llh,<lat>,<lon>,<h>,<radius>,<invf>,<utmZone><heightUnits> -jar jtransform_thin.jar

example#1a:
java -Dparms=llh,-33.8688,151.2093,100.0,6378160.0,298.25,auto -jar jtransform_thin.jar
(height units not specified;defaults to meters)
java -Dparms=llh,-33.8688,151.2093,100.0,6378160.0,298.25,auto,ift -jar jtransform_thin.jar
(height units specified)

Format#1b (lat-long-orthometric height conversion)
java -Dparms=llH,<lat>,<lon>,<H>,<inDatum>,<outDatum><spcZone><utmZone> <inVertDatum> <outVertDatum><heightUnits> -jar jtransform_thin.jar

example#1b:
java -Dparms=llH,40.0,-80.0,100.0,NAD83(2011),NAD83(2011),3702,auto,NAVD88,NAVD88 -jar jtransform_thin.jar
(height units not specified;defaults to meters)
java -Dparms=llH,40.0,-80.0,100.0,NAD83(2011),NAD83(2011),3702,auto,NAVD88,NAVD88,ift -jar jtransform_thin.jar
(height units specified. However, there'll be no change in converted coordinates as they don't depend on orthometric height )

Format#2 (SPC-ellipsoid height conversion):
java -Dparms=spch,<spcZone>,<northing>,<easting>,<units>,<inDatum> <outDatum><utmZone><h><heightUnits><destZone>-jar jtransform_thin.jar

example#2:
java -Dparms=spch,2402,173099.419,503626.812,m,NAD83(2011),NAD83(2011),auto,100.0 -jar jtransform_thin.jar
(height units not specified;defaults to meters. No change in SPC coordinates as no transformation is done.)
java -Dparms=spch,2402,173099.419,503626.812,m,NAD83(2011),NAD83(2011),auto,100.0,ift -jar jtransform_thin.jar
(only the height units specified;there will be a change in combined factor and xyz coordinate )

Format#2a (SPC-ellipsoid height conversion; use this format to convert SPC from one zone to the other):
java -Dparms=spch,<spcZone>,<northing>,<easting>,<units>,<inDatum> <outDatum><utmZone><h><destZone><heightUnits> -jar jtransform_thin.jar

example#2a:
java -Dparms=spch,2402,173099.419,503626.812,m,NAD83(2011),NAD83(2011),auto,100.0,2401 -jar jtransform_thin.jar
(only the destination zone provided)
java -Dparms=spch,2402,173099.419,503626.812,m,NAD83(2011),NAD83(2011),auto,100.0,2401,ift -jar jtransform_thin.jar
(both the destination zone and height units provided)

Format#2b (SPC-orthometric height conversion):
java -Dparms=spcH,<spcZone>,<northing>,<easting>,<units>,<inDatum> <outDatum><utmZone><H><inVertDatum> <outVertDatum><destZone><heightUnits> -jar jtransform_thin.jar

example#2b:
java -Dparms=spcH,2402,173099.419,503626.812,m,NAD83(2011),NAD83(2011),auto,100.0,NAVD88,NAVD88 -jar jtransform_thin.jar
(height units not specified;defaults to meters. No change in SPC coordinates as no transformation is done.)

Example#2c (SPC-orthometric height conversion; use this format to convert SPC from one zone to the other):
java -Dparms=spcH,2402,173099.419,503626.812,m,NAD83(2011),NAD83(2011),auto,100.0,NAVD88,NAVD88,2401 -jar jtransform_thin.jar
(only the destination zone provided)
java -Dparms=spcH,2402,173099.419,503626.812,m,NAD83(2011),NAD83(2011),auto,100.0,NAVD88,NAVD88,2401,ift -jar jtransform_thin.jar
(both the destination zone and height units provided)


Format#3 (UTM-ellipsoid height conversion)
java -Dparms=utmh,<utmZone>,<northing>,<easting>,<hemi>,<inDatum>,<outDatum>,<spcZone><h><destZone><heightUnits> -jar jtransform_thin.jar

Example#3
java -Dparms=utmh,15,4138641.144,547883.655,N,NAD83(2011),NAD83(2011),2402,100.0 -jar jtransform_thin.jar
(height units not specified;defaults to meters. No change in UTM coordinates as no transformation is done.)

Example#3a (UTM-ellipsoid height conversion; use this format to convert UTM from one zone to the other):
java -Dparms=utmh,15,4138641.144,547883.655,N,NAD83(2011),NAD83(2011),2402,100.0,14 -jar jtransform_thin.jar
(only the destination zone provided)
java -Dparms=utmh,15,4138641.144,547883.655,N,NAD83(2011),NAD83(2011),2402,100.0,14,ift -jar jtransform_thin.jar
(both the destination zone and height units provided)

Format#3b (UTM-orthometric height conversion)
java -Dparms=utmH,<utmZone>,<northing>,<easting>,<hemi>,<inDatum>,<outDatum>,<spcZone><H><inVertDatum><outVertDatum><destZone><heightUnits> -jar jtransform_thin.jar

Example#3b
java -Dparms=utmH,15,4138641.144,547883.655,N,NAD83(2011),NAD83(2011),2402,100.0,NAVD88,NAVD88 -jar jtransform_thin.jar
(height units not specified;defaults to meters. No change in UTM coordinates as no transformation is done.)
Example#3c
java -Dparms=utmH,15,4138641.144,547883.655,N,NAD83(2011),NAD83(2011),2402,100.0,NAVD88,NAVD88,14 -jar jtransform_thin.jar
(only the destination zone provided)
java -Dparms=utmH,15,4138641.144,547883.655,N,NAD83(2011),NAD83(2011),2402,100.0,NAVD88,NAVD88,14,ift -jar jtransform_thin.jar
(both the destination zone and height units provided)

Format#3d (UTM-ellipsoid height conversion; use this format for international coordinates)
java -Dparms=utmh,<utmZone>,<northing>,<easting>,<hemi>,<radius> <invf><eht><destZone><heightUnits> -jar jtransform_thin.jar

Example#3d
java -Dparms=utmh,56,6250935.338,334368.032,S,6378160.0,298.25,100.0 -jar jtransform_thin.jar
(height units not specified;defaults to meters. No change in UTM coordinates as no transformation is done.)
java -Dparms=utmh,56,6250935.338,334368.032,S,6378160.0,298.25,100.0,55 -jar jtransform_thin.jar
(only the destination zone provided)
java -Dparms=utmh,56,6250935.338,334368.032,S,6378160.0,298.25,100.0,55,ift -jar jtransform_thin.jar
(both the destination zone and height units provided)

Format#4 (USNG-ellipsoid height conversion)
java -Dparms=usngh,<usng>,<inDatum>,<outDatum>,<spcZone><h><heightUnits> -jar jtransform_thin.jar

Example#4
java -Dparms=usngh,15SWB4788338641,nad83(2011),nad83(2011),2402,100.0 -jar jtransform_thin.jar
(height units not specified;defaults to meters)
java -Dparms=usngh,15SWB4788338641,nad83(2011),nad83(2011),2402,100.0,ift -jar jtransform_thin.jar
(height units provided)

Format#4a (USNG-orthometric height conversion)
java -Dparms=usngH,<usng>,<inDatum>,<outDatum>,<spcZone><H><inVertDatum><outVertDatum><heightUnits> -jar jtransform_thin.jar

Example#4a
java -Dparms=usngH,15SWB4788338641,nad83(2011),nad83(2011),2402,100.0,NAVD88,NAVD88 -jar jtransform_thin.jar
(height units not specified;defaults to meters)
java -Dparms=usngH,15SWB4788338641,nad83(2011),nad83(2011),2402,100.0,NAVD88,NAVD88,ift -jar jtransform_thin.jar
(height units provided)

Command format#4b (USNG-ellipsoid height; use this format for an international coordinate)
java -Dparms=usngh,<usng>,<radius>,<invf><h><heightUnits> -jar jtransform_thin.jar

Example#4b
java -Dparms=usngh,56HLH3436850935,6378160.0,298.25,100.0 -jar jtransform_thin.jar
(height units not specified;defaults to meters)
java -Dparms=usngh,56HLH3436850935,6378160.0,298.25,100.0,ift -jar jtransform_thin.jar
(height units provided)

Format#5 (XYZ conversion)
java -Dparms=xyz,<x>,<y>,<z>,<inDatum>,<outDatum>,<spcZone>,<utmZone>

Example#5
java -Dparms=xyz,-217683.881,-5068933.259,3852162.058,NAD83(2011),NAD83(2011),2402,auto -jar jtransform_thin.jar

Command format#5a (XYZ conversion for an international coordinate)
java -Dparms=xyz,<x>,<y>,<z>,<radius>,<invf>,><utmZone>

Example#5a
java -Dparms=xyz,-4646068.143,2553215.614,-3534384.646,6378160.0,298.25,auto -jar jtransform_thin.jar

Sample output:
{
"ID":"1644348734437",
"nadconVersion":"5.0",
"vertconVersion":"3.0",
"srcDatum":"NAD83(1986)",
"destDatum":"NAD83(1986)",
"srcVertDatum":"N/A",
"destVertDatum":"N/A",
"srcLat":"40.0000000000",
"srcLatDms":"N400000.00000",
"destLat":"40.0000000000",
"destLatDms":"N400000.00000",
"sigLat":"0.000000",
"srcLon":"-80.0000000000",
"srcLonDms":"W0800000.00000",
"destLon":"-80.0000000000",
"destLonDms":"W0800000.00000",
"sigLon":"0.000000",
"heightUnits":"m",
"srcEht":"100.000",
"destEht":"100.000",
"sigEht":"0.000",
"srcOrthoht":"N/A",
"destOrthoht":"N/A",
"sigOrthoht":"N/A",
"spcZone":"PA S-3702",
"spcNorthing_m":"76,470.584",
"spcEasting_m":"407,886.482",
"spcNorthing_usft":"250,887.243",
"spcEasting_usft":"1,338,207.567",
"spcNorthing_ift":"250,887.744",
"spcEasting_ift":"1,338,210.244",
"spcConvergence":"-01 27 35.22",
"spcScaleFactor":"0.99999024",
"spcCombinedFactor":"0.99997455",
"utmZone":"UTM Zone 17",
"utmNorthing":"4,428,236.065",
"utmEasting":"585,360.462",
"utmConvergence":"00 38 34.17",
"utmScaleFactor":"0.99968970",
"utmCombinedFactor":"0.99967402",
"x":"849,623.061",
"y":"-4,818,451.818",
"z":"4,078,049.851",
"usng":"17TNE8536028236"
}

Using NCAT in a java program
__________________________________________

The download archive contains the source code being used for NCAT command line version. The filename is CLDriver.java.
Also included in the archive is a library jar, jtransform_thin.jar, being used for the command line version and a 
companion javadoc to support custom output formats or conversions.












