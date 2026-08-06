%Dan Martin
%Michigan State Plane All Zones Coordinate Conversion Tool


%initial formatting
clear
clc
format long g
disp('Michigan State Plane Coordinate Conversion Tool')
disp('')

%pick zone
y=input(sprintf('Enter 1 for North Zone\nEnter 2 for Central Zone\nEnter 3 for South Zone\nEnter 4 to quit: '));
disp('')

if (y==1) %NORTH ZONE
%constants
B0=46.2853056176;
R0=6108308.6036;
L0=87;
E0=8000000;
N0=166935.2398;
sinB0=sind(B0);

%coefficients
L1=111146.0908;
L2=9.76397;
L3=5.62053;
L4=0.025777;
L5=0.0007325;
G1=8.997167538*10^-6;
G2=-7.11123*10^-15;
G3=-3.68190*10^-20;
G4=-1.3725*10^-27;
G5=8.019*10^-35;
F1=0.999902834466;
F2=1.22919*10^-14;
F3=6.7*10^-22;

elseif (y==2) %CENTRAL ZONE
%constants
B0=44.9433587575;
R0=6400902.4399;
L0=(84+22/60);
E0=6000000;
N0=180757.7922;
sinB0=sind(B0);

%coefficients
L1=111120.9691;
L2=9.77091;
L3=5.62494;
L4=0.023788;
L5=0;
G1=8.999201531*10^-6;
G2=-7.12032*10^-15;
G3=-3.68711*10^-20;
G4=-1.3161*10^-27;
G5=0;
F1=0.999912706253;
F2=1.22939*10^-14;
F3=6.25*10^-22;

elseif (y==3) %SOUTH ZONE
%constants
B0=42.8850151357;
R0=6877323.4058;
L0=(84+22/60);
E0=4000000;
N0=153843.8848;
sinB0=sind(B0);

%coefficients
L1=111080.1507;
L2=9.73761;
L3=5.63002;
L4=0.022802;
L5=0;
G1=9.002508421*10^-6;
G2=-7.10459*10^-15;
G3=-3.69552*10^-20;
G4=-1.2067*10^-27;
G5=0;
F1=0.999906878420;
F2=1.23000*10^-14;
F3=5.87*10^-22;

elseif (y==4)
return

endif

%conversion method
x=input(sprintf('Enter 1 for Geodetic to SPC\nEnter 2 for SPC to Geodetic\nEnter 3 to quit: '));
disp('')

if (x==1) %geodetic to SPC
%direct inputs (degrees)
phi1=input('Input a latitude value in decimal degrees (north is positive): ');
lam1=input('Input a longitude value in decimal degrees (west is positive): ');
Elev1=input('Input a Orhtometric Height (feet): ');
Gsm=input('Input the Geoid Seperation (meters): ');
Gsf=Gsm/0.3048;
disp('')
disp(sprintf('If you would like to find azimuth and distance between two points,\ninput another point. If not, enter 0 three times and ignore point 2 results.')) 
disp('')
phi2=input('Input a latitude value in decimal degrees (north is positive): ');
lam2=input('Input a longitude value in decimal degrees (west is positive): ');
Elev2=input('Input a Orhtometric Height (feet): ');
disp('')

%---------------DIRECT COMPUTATIONS---------------

%direct conversion pt.1
%display('direct conversion pt.1');
gam1=(L0-lam1)*sinB0;
dphi1=phi1-B0;
u1=L1*dphi1+L2*dphi1^2+L3*dphi1^3+L4*dphi1^4+L5*dphi1^5;
k1=F1+F2*u1^2+F3*u1^3;
R1=R0-u1;
Ep1=R1*sin(gam1*(pi/180));
Np1=u1+Ep1*tan((gam1/2)*(pi/180));
N1=(Np1+N0)*3.280839895 ;
E1=(Ep1+E0)*3.280839895 ;
display('');

%direct conversion pt.2
%display('direct conversion pt.2');
gam2=(L0-lam2)*sinB0;
dphi2=phi2-B0;
u2=L1*dphi2+L2*dphi2^2+L3*dphi2^3+L4*dphi2^4+L5*dphi2^5;
k2=F1+F2*u2^2+F3*u2^3;
R2=R0-u2;
Ep2=R2*sin(gam2*(pi/180));
Np2=u2+Ep2*tan((gam2/2)*(pi/180));
N2=(Np2+N0)*3.280839895;
E2=(Ep2+E0)*3.280839895;
display('');

%Elevation Factor
R=20906000;
EF1=(R/(R+Elev1+Gsf));
EF2=(R/(R+Elev2+Gsf));

%distance/azimuth computations
%display('distance/azimuth computations');
CSF1=k1*EF1;
CSF2=k2*EF2;
dGRID=sqrt((E1-E2)^2+(N1-N2)^2);
dGROUND=dGRID/((CSF1+CSF2)/2);
t=atan2((E2-E1),(N2-N1))*(180/pi);
p1=N1-N0;
d12=(25.4*(p1+(N2-N1)/3)*(E2-E1)*10^(-10))/3600; %degrees
a=t-d12+gam1;

%display answers
display('')
display('')
display('----------------------------------------------------')
display('Results:')
display('')
display('Point 1 Output:')
fprintf('N = %9.3f ift\n',N1)
fprintf('E = %9.3f ift\n',E1)
fprintf('H = %7.3f ift\n',Elev1)
fprintf('Lat = %9.6f degrees\n',phi1)
fprintf('Long = %9.6f degrees\n',lam1)
fprintf('Convergence Angle = %8.6f degrees\n',gam1)
fprintf('Scale Factor = %9.8f \n',k1)
fprintf('Combined Scale Factor = %9.8f \n',CSF1)
display('')
display('Point 2 Output:')
fprintf('N = %9.3f ift\n',N2)
fprintf('E = %9.3f ift\n',E2)
fprintf('H = %7.3f ift\n',Elev2)
fprintf('Lat = %9.6f degrees\n',phi2)
fprintf('Long = %9.6f degrees\n',lam2)
fprintf('Convergence Angle = %8.6f degrees\n',gam2)
fprintf('Scale Factor = %9.8f \n',k2)
fprintf('Combined Scale Factor = %9.8f \n',CSF2)
display('')
display('Distance/Azimuth:')
fprintf('Grid Distance = %9.3f ift\n',dGRID)
fprintf('Ground Distance = %9.3f ift\n',dGROUND)
fprintf('Grid Azimuth Pt.1 --> Pt.2 = %9.6f degrees\n',t)
fprintf('Geodetic Azimuth Pt.1 --> Pt.2 = %9.6f degrees\n',a)
display('')

elseif (x==2) %SPC to geodetic
%inverse inputs (feet)
N1f=input('Input the northing value (in feet): ');
E1f=input('Input the easting value (in feet): ' );
Elev1=input('Input a Orhtometric Height (feet): ');
Gsm=input('Input the Geoid Seperation (meters): ');
Gsf=Gsm/0.3048;
disp('')
disp(sprintf('If you would like to find azimuth and distance between two points,\ninput another point. If not, enter 0 three times and ignore point 2 results.')) 
disp('')
N2f=input('Input the northing value (in feet): ');
E2f=input('Input the easting value (in feet): ');
Elev2=input('Input a Orhtometric Height (feet): ');
disp('')

%---------------INVERSE COMPUTATIONS---------------

%convert to meters for compuation
N1=N1f*0.3048;
E1=E1f*0.3048;
N2=N2f*0.3048;
E2=E2f*0.3048;
display('')

%inverse conversion pt.1
%display('inverse conversion pt.1');
Np1=N1-N0;
Ep1=E1-E0;
Rp3=R0-Np1;
gam3=atan(Ep1/Rp3)*(180/pi);
u3=Np1-Ep1*tan((gam3/2)*(pi/180));
k3=F1+F2*u3^2+F3*u3^3;
dphi3=G1*u3+G2*u3^2+G3*u3^3+G4*u3^4+G5*u3^5;
Phi1=B0+dphi3;
Lam1=L0-(gam3/sinB0);
display('');

%inverse conversion pt.2
%display('inverse conversion pt.2');
Np2=N2-N0;
Ep2=E2-E0;
Rp4=R0-Np2;
gam4=atan(Ep2/Rp4)*(180/pi);
u4=Np2-Ep2*tan((gam4/2)*(pi/180));
k4=F1+F2*u4^2+F3*u4^3;
dphi4=G1*u4+G2*u4^2+G3*u4^3+G4*u4^4+G5*u4^5;
Phi2=B0+dphi4;
Lam2=L0-(gam4/sinB0);
display('');

%Elevation Factor
R=20906000;
EF1=(R/(R+Elev1+Gsf));
EF2=(R/(R+Elev2+Gsf));

%distance/azimuth computations
%display('distance/azimuth computations');
CSF1=k3*EF1;
CSF2=k4*EF2;
dGRID=sqrt((E1-E2)^2+(N1-N2)^2)/0.3048;
dGROUND=dGRID/((CSF1+CSF2)/2);
t=atan2((E2-E1),(N2-N1))*(180/pi);
p1=N1-N0;
d12=(25.4*(p1+(N2-N1)/3)*(E2-E1)*10^(-10))/3600; %degrees
a=t-d12+gam3;

%display answers
display('')
display('')
display('----------------------------------------------------')
display('Results:')
display('')
display('Point 1 Output:')
fprintf('N = %9.3f ift\n',N1f)
fprintf('E = %9.3f ift\n',E1f)
fprintf('H = %7.3f ift\n',Elev1)
fprintf('Lat = %9.6f degrees\n',Phi1)
fprintf('Long = %9.6f degrees\n',Lam1)
fprintf('Convergence Angle = %8.6f degrees\n',gam3)
fprintf('Scale Factor = %9.8f \n',k3)
fprintf('Combined Scale Factor = %9.8f \n',CSF1)
display('')
display('Point 2 Output:')
fprintf('N = %9.3f ift\n',N2f)
fprintf('E = %9.3f ift\n',E2f)
fprintf('H = %7.3f ift\n',Elev2)
fprintf('Lat = %9.6f degrees\n',Phi2)
fprintf('Long = %9.6f degrees\n',Lam2)
fprintf('Convergence Angle = %8.6f degrees\n',gam4)
fprintf('Scale Factor = %9.8f \n',k4)
fprintf('Combined Scale Factor = %9.8f \n',CSF2)
display('')
display('Distance/Azimuth:')
fprintf('Grid Distance = %9.3f ift\n',dGRID)
fprintf('Ground Distance = %9.3f ift\n',dGROUND)
fprintf('Grid Azimuth Pt.1 --> Pt.2 = %9.6f degrees\n',t)
fprintf('Geodetic Azimuth Pt.1 --> Pt.2 = %9.6f degrees\n',a)
display('')

elseif (x==3) %quit
return

endif
