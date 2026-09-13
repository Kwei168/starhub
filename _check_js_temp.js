
/**
 * Minified by jsDelivr using Terser v5.37.0.
 * Original file: /npm/qrcode-generator@1.4.4/qrcode.js
 *
 * Do NOT use SRI with dynamically generated files! More information: https://www.jsdelivr.com/using-sri-with-dynamic-files
 */
var qrcode=function(){var t=function(t,r){var e=t,n=g[r],o=null,i=0,a=null,u=[],f={},c=function(t,r){o=function(t){for(var r=new Array(t),e=0;e<t;e+=1){r[e]=new Array(t);for(var n=0;n<t;n+=1)r[e][n]=null}return r}(i=4*e+17),l(0,0),l(i-7,0),l(0,i-7),s(),h(),d(t,r),e>=7&&v(t),null==a&&(a=p(e,n,u)),w(a,r)},l=function(t,r){for(var e=-1;e<=7;e+=1)if(!(t+e<=-1||i<=t+e))for(var n=-1;n<=7;n+=1)r+n<=-1||i<=r+n||(o[t+e][r+n]=0<=e&&e<=6&&(0==n||6==n)||0<=n&&n<=6&&(0==e||6==e)||2<=e&&e<=4&&2<=n&&n<=4)},h=function(){for(var t=8;t<i-8;t+=1)null==o[t][6]&&(o[t][6]=t%2==0);for(var r=8;r<i-8;r+=1)null==o[6][r]&&(o[6][r]=r%2==0)},s=function(){for(var t=B.getPatternPosition(e),r=0;r<t.length;r+=1)for(var n=0;n<t.length;n+=1){var i=t[r],a=t[n];if(null==o[i][a])for(var u=-2;u<=2;u+=1)for(var f=-2;f<=2;f+=1)o[i+u][a+f]=-2==u||2==u||-2==f||2==f||0==u&&0==f}},v=function(t){for(var r=B.getBCHTypeNumber(e),n=0;n<18;n+=1){var a=!t&&1==(r>>n&1);o[Math.floor(n/3)][n%3+i-8-3]=a}for(n=0;n<18;n+=1){a=!t&&1==(r>>n&1);o[n%3+i-8-3][Math.floor(n/3)]=a}},d=function(t,r){for(var e=n<<3|r,a=B.getBCHTypeInfo(e),u=0;u<15;u+=1){var f=!t&&1==(a>>u&1);u<6?o[u][8]=f:u<8?o[u+1][8]=f:o[i-15+u][8]=f}for(u=0;u<15;u+=1){f=!t&&1==(a>>u&1);u<8?o[8][i-u-1]=f:u<9?o[8][15-u-1+1]=f:o[8][15-u-1]=f}o[i-8][8]=!t},w=function(t,r){for(var e=-1,n=i-1,a=7,u=0,f=B.getMaskFunction(r),c=i-1;c>0;c-=2)for(6==c&&(c-=1);;){for(var g=0;g<2;g+=1)if(null==o[n][c-g]){var l=!1;u<t.length&&(l=1==(t[u]>>>a&1)),f(n,c-g)&&(l=!l),o[n][c-g]=l,-1==(a-=1)&&(u+=1,a=7)}if((n+=e)<0||i<=n){n-=e,e=-e;break}}},p=function(t,r,e){for(var n=A.getRSBlocks(t,r),o=b(),i=0;i<e.length;i+=1){var a=e[i];o.put(a.getMode(),4),o.put(a.getLength(),B.getLengthInBits(a.getMode(),t)),a.write(o)}var u=0;for(i=0;i<n.length;i+=1)u+=n[i].dataCount;if(o.getLengthInBits()>8*u)throw"code length overflow. ("+o.getLengthInBits()+">"+8*u+")";for(o.getLengthInBits()+4<=8*u&&o.put(0,4);o.getLengthInBits()%8!=0;)o.putBit(!1);for(;!(o.getLengthInBits()>=8*u||(o.put(236,8),o.getLengthInBits()>=8*u));)o.put(17,8);return function(t,r){for(var e=0,n=0,o=0,i=new Array(r.length),a=new Array(r.length),u=0;u<r.length;u+=1){var f=r[u].dataCount,c=r[u].totalCount-f;n=Math.max(n,f),o=Math.max(o,c),i[u]=new Array(f);for(var g=0;g<i[u].length;g+=1)i[u][g]=255&t.getBuffer()[g+e];e+=f;var l=B.getErrorCorrectPolynomial(c),h=k(i[u],l.getLength()-1).mod(l);for(a[u]=new Array(l.getLength()-1),g=0;g<a[u].length;g+=1){var s=g+h.getLength()-a[u].length;a[u][g]=s>=0?h.getAt(s):0}}var v=0;for(g=0;g<r.length;g+=1)v+=r[g].totalCount;var d=new Array(v),w=0;for(g=0;g<n;g+=1)for(u=0;u<r.length;u+=1)g<i[u].length&&(d[w]=i[u][g],w+=1);for(g=0;g<o;g+=1)for(u=0;u<r.length;u+=1)g<a[u].length&&(d[w]=a[u][g],w+=1);return d}(o,n)};f.addData=function(t,r){var e=null;switch(r=r||"Byte"){case"Numeric":e=M(t);break;case"Alphanumeric":e=x(t);break;case"Byte":e=m(t);break;case"Kanji":e=L(t);break;default:throw"mode:"+r}u.push(e),a=null},f.isDark=function(t,r){if(t<0||i<=t||r<0||i<=r)throw t+","+r;return o[t][r]},f.getModuleCount=function(){return i},f.make=function(){if(e<1){for(var t=1;t<40;t++){for(var r=A.getRSBlocks(t,n),o=b(),i=0;i<u.length;i++){var a=u[i];o.put(a.getMode(),4),o.put(a.getLength(),B.getLengthInBits(a.getMode(),t)),a.write(o)}var g=0;for(i=0;i<r.length;i++)g+=r[i].dataCount;if(o.getLengthInBits()<=8*g)break}e=t}c(!1,function(){for(var t=0,r=0,e=0;e<8;e+=1){c(!0,e);var n=B.getLostPoint(f);(0==e||t>n)&&(t=n,r=e)}return r}())},f.createTableTag=function(t,r){t=t||2;var e="";e+='<table style="',e+=" border-width: 0px; border-style: none;",e+=" border-collapse: collapse;",e+=" padding: 0px; margin: "+(r=void 0===r?4*t:r)+"px;",e+='">',e+="<tbody>";for(var n=0;n<f.getModuleCount();n+=1){e+="<tr>";for(var o=0;o<f.getModuleCount();o+=1)e+='<td style="',e+=" border-width: 0px; border-style: none;",e+=" border-collapse: collapse;",e+=" padding: 0px; margin: 0px;",e+=" width: "+t+"px;",e+=" height: "+t+"px;",e+=" background-color: ",e+=f.isDark(n,o)?"#000000":"#ffffff",e+=";",e+='"/>';e+="</tr>"}return e+="</tbody>",e+="</table>"},f.createSvgTag=function(t,r,e,n){var o={};"object"==typeof arguments[0]&&(t=(o=arguments[0]).cellSize,r=o.margin,e=o.alt,n=o.title),t=t||2,r=void 0===r?4*t:r,(e="string"==typeof e?{text:e}:e||{}).text=e.text||null,e.id=e.text?e.id||"qrcode-description":null,(n="string"==typeof n?{text:n}:n||{}).text=n.text||null,n.id=n.text?n.id||"qrcode-title":null;var i,a,u,c,g=f.getModuleCount()*t+2*r,l="";for(c="l"+t+",0 0,"+t+" -"+t+",0 0,-"+t+"z ",l+='<svg version="1.1" xmlns="http://www.w3.org/2000/svg"',l+=o.scalable?"":' width="'+g+'px" height="'+g+'px"',l+=' viewBox="0 0 '+g+" "+g+'" ',l+=' preserveAspectRatio="xMinYMin meet"',l+=n.text||e.text?' role="img" aria-labelledby="'+y([n.id,e.id].join(" ").trim())+'"':"",l+=">",l+=n.text?'<title id="'+y(n.id)+'">'+y(n.text)+"</title>":"",l+=e.text?'<description id="'+y(e.id)+'">'+y(e.text)+"</description>":"",l+='<rect width="100%" height="100%" fill="white" cx="0" cy="0"/>',l+='<path d="',a=0;a<f.getModuleCount();a+=1)for(u=a*t+r,i=0;i<f.getModuleCount();i+=1)f.isDark(a,i)&&(l+="M"+(i*t+r)+","+u+c);return l+='" stroke="transparent" fill="black"/>',l+="</svg>"},f.createDataURL=function(t,r){t=t||2,r=void 0===r?4*t:r;var e=f.getModuleCount()*t+2*r,n=r,o=e-r;return I(e,e,(function(r,e){if(n<=r&&r<o&&n<=e&&e<o){var i=Math.floor((r-n)/t),a=Math.floor((e-n)/t);return f.isDark(a,i)?0:1}return 1}))},f.createImgTag=function(t,r,e){t=t||2,r=void 0===r?4*t:r;var n=f.getModuleCount()*t+2*r,o="";return o+="<img",o+=' src="',o+=f.createDataURL(t,r),o+='"',o+=' width="',o+=n,o+='"',o+=' height="',o+=n,o+='"',e&&(o+=' alt="',o+=y(e),o+='"'),o+="/>"};var y=function(t){for(var r="",e=0;e<t.length;e+=1){var n=t.charAt(e);switch(n){case"<":r+="&lt;";break;case">":r+="&gt;";break;case"&":r+="&amp;";break;case'"':r+="&quot;";break;default:r+=n}}return r};return f.createASCII=function(t,r){if((t=t||1)<2)return function(t){t=void 0===t?2:t;var r,e,n,o,i,a=1*f.getModuleCount()+2*t,u=t,c=a-t,g={"██":"█","█ ":"▀"," █":"▄","  ":" "},l={"██":"▀","█ ":"▀"," █":" ","  ":" "},h="";for(r=0;r<a;r+=2){for(n=Math.floor((r-u)/1),o=Math.floor((r+1-u)/1),e=0;e<a;e+=1)i="█",u<=e&&e<c&&u<=r&&r<c&&f.isDark(n,Math.floor((e-u)/1))&&(i=" "),u<=e&&e<c&&u<=r+1&&r+1<c&&f.isDark(o,Math.floor((e-u)/1))?i+=" ":i+="█",h+=t<1&&r+1>=c?l[i]:g[i];h+="\n"}return a%2&&t>0?h.substring(0,h.length-a-1)+Array(a+1).join("▀"):h.substring(0,h.length-1)}(r);t-=1,r=void 0===r?2*t:r;var e,n,o,i,a=f.getModuleCount()*t+2*r,u=r,c=a-r,g=Array(t+1).join("██"),l=Array(t+1).join("  "),h="",s="";for(e=0;e<a;e+=1){for(o=Math.floor((e-u)/t),s="",n=0;n<a;n+=1)i=1,u<=n&&n<c&&u<=e&&e<c&&f.isDark(o,Math.floor((n-u)/t))&&(i=0),s+=i?g:l;for(o=0;o<t;o+=1)h+=s+"\n"}return h.substring(0,h.length-1)},f.renderTo2dContext=function(t,r){r=r||2;for(var e=f.getModuleCount(),n=0;n<e;n++)for(var o=0;o<e;o++)t.fillStyle=f.isDark(n,o)?"black":"white",t.fillRect(n*r,o*r,r,r)},f};t.stringToBytes=(t.stringToBytesFuncs={default:function(t){for(var r=[],e=0;e<t.length;e+=1){var n=t.charCodeAt(e);r.push(255&n)}return r}}).default,t.createStringToBytes=function(t,r){var e=function(){for(var e=S(t),n=function(){var t=e.read();if(-1==t)throw"eof";return t},o=0,i={};;){var a=e.read();if(-1==a)break;var u=n(),f=n()<<8|n();i[String.fromCharCode(a<<8|u)]=f,o+=1}if(o!=r)throw o+" != "+r;return i}(),n="?".charCodeAt(0);return function(t){for(var r=[],o=0;o<t.length;o+=1){var i=t.charCodeAt(o);if(i<128)r.push(i);else{var a=e[t.charAt(o)];"number"==typeof a?(255&a)==a?r.push(a):(r.push(a>>>8),r.push(255&a)):r.push(n)}}return r}};var r,e,n,o,i,a=1,u=2,f=4,c=8,g={L:1,M:0,Q:3,H:2},l=0,h=1,s=2,v=3,d=4,w=5,p=6,y=7,B=(r=[[],[6,18],[6,22],[6,26],[6,30],[6,34],[6,22,38],[6,24,42],[6,26,46],[6,28,50],[6,30,54],[6,32,58],[6,34,62],[6,26,46,66],[6,26,48,70],[6,26,50,74],[6,30,54,78],[6,30,56,82],[6,30,58,86],[6,34,62,90],[6,28,50,72,94],[6,26,50,74,98],[6,30,54,78,102],[6,28,54,80,106],[6,32,58,84,110],[6,30,58,86,114],[6,34,62,90,118],[6,26,50,74,98,122],[6,30,54,78,102,126],[6,26,52,78,104,130],[6,30,56,82,108,134],[6,34,60,86,112,138],[6,30,58,86,114,142],[6,34,62,90,118,146],[6,30,54,78,102,126,150],[6,24,50,76,102,128,154],[6,28,54,80,106,132,158],[6,32,58,84,110,136,162],[6,26,54,82,110,138,166],[6,30,58,86,114,142,170]],e=1335,n=7973,i=function(t){for(var r=0;0!=t;)r+=1,t>>>=1;return r},(o={}).getBCHTypeInfo=function(t){for(var r=t<<10;i(r)-i(e)>=0;)r^=e<<i(r)-i(e);return 21522^(t<<10|r)},o.getBCHTypeNumber=function(t){for(var r=t<<12;i(r)-i(n)>=0;)r^=n<<i(r)-i(n);return t<<12|r},o.getPatternPosition=function(t){return r[t-1]},o.getMaskFunction=function(t){switch(t){case l:return function(t,r){return(t+r)%2==0};case h:return function(t,r){return t%2==0};case s:return function(t,r){return r%3==0};case v:return function(t,r){return(t+r)%3==0};case d:return function(t,r){return(Math.floor(t/2)+Math.floor(r/3))%2==0};case w:return function(t,r){return t*r%2+t*r%3==0};case p:return function(t,r){return(t*r%2+t*r%3)%2==0};case y:return function(t,r){return(t*r%3+(t+r)%2)%2==0};default:throw"bad maskPattern:"+t}},o.getErrorCorrectPolynomial=function(t){for(var r=k([1],0),e=0;e<t;e+=1)r=r.multiply(k([1,C.gexp(e)],0));return r},o.getLengthInBits=function(t,r){if(1<=r&&r<10)switch(t){case a:return 10;case u:return 9;case f:case c:return 8;default:throw"mode:"+t}else if(r<27)switch(t){case a:return 12;case u:return 11;case f:return 16;case c:return 10;default:throw"mode:"+t}else{if(!(r<41))throw"type:"+r;switch(t){case a:return 14;case u:return 13;case f:return 16;case c:return 12;default:throw"mode:"+t}}},o.getLostPoint=function(t){for(var r=t.getModuleCount(),e=0,n=0;n<r;n+=1)for(var o=0;o<r;o+=1){for(var i=0,a=t.isDark(n,o),u=-1;u<=1;u+=1)if(!(n+u<0||r<=n+u))for(var f=-1;f<=1;f+=1)o+f<0||r<=o+f||0==u&&0==f||a==t.isDark(n+u,o+f)&&(i+=1);i>5&&(e+=3+i-5)}for(n=0;n<r-1;n+=1)for(o=0;o<r-1;o+=1){var c=0;t.isDark(n,o)&&(c+=1),t.isDark(n+1,o)&&(c+=1),t.isDark(n,o+1)&&(c+=1),t.isDark(n+1,o+1)&&(c+=1),0!=c&&4!=c||(e+=3)}for(n=0;n<r;n+=1)for(o=0;o<r-6;o+=1)t.isDark(n,o)&&!t.isDark(n,o+1)&&t.isDark(n,o+2)&&t.isDark(n,o+3)&&t.isDark(n,o+4)&&!t.isDark(n,o+5)&&t.isDark(n,o+6)&&(e+=40);for(o=0;o<r;o+=1)for(n=0;n<r-6;n+=1)t.isDark(n,o)&&!t.isDark(n+1,o)&&t.isDark(n+2,o)&&t.isDark(n+3,o)&&t.isDark(n+4,o)&&!t.isDark(n+5,o)&&t.isDark(n+6,o)&&(e+=40);var g=0;for(o=0;o<r;o+=1)for(n=0;n<r;n+=1)t.isDark(n,o)&&(g+=1);return e+=Math.abs(100*g/r/r-50)/5*10},o),C=function(){for(var t=new Array(256),r=new Array(256),e=0;e<8;e+=1)t[e]=1<<e;for(e=8;e<256;e+=1)t[e]=t[e-4]^t[e-5]^t[e-6]^t[e-8];for(e=0;e<255;e+=1)r[t[e]]=e;var n={glog:function(t){if(t<1)throw"glog("+t+")";return r[t]},gexp:function(r){for(;r<0;)r+=255;for(;r>=256;)r-=255;return t[r]}};return n}();function k(t,r){if(void 0===t.length)throw t.length+"/"+r;var e=function(){for(var e=0;e<t.length&&0==t[e];)e+=1;for(var n=new Array(t.length-e+r),o=0;o<t.length-e;o+=1)n[o]=t[o+e];return n}(),n={getAt:function(t){return e[t]},getLength:function(){return e.length},multiply:function(t){for(var r=new Array(n.getLength()+t.getLength()-1),e=0;e<n.getLength();e+=1)for(var o=0;o<t.getLength();o+=1)r[e+o]^=C.gexp(C.glog(n.getAt(e))+C.glog(t.getAt(o)));return k(r,0)},mod:function(t){if(n.getLength()-t.getLength()<0)return n;for(var r=C.glog(n.getAt(0))-C.glog(t.getAt(0)),e=new Array(n.getLength()),o=0;o<n.getLength();o+=1)e[o]=n.getAt(o);for(o=0;o<t.getLength();o+=1)e[o]^=C.gexp(C.glog(t.getAt(o))+r);return k(e,0).mod(t)}};return n}var A=function(){var t=[[1,26,19],[1,26,16],[1,26,13],[1,26,9],[1,44,34],[1,44,28],[1,44,22],[1,44,16],[1,70,55],[1,70,44],[2,35,17],[2,35,13],[1,100,80],[2,50,32],[2,50,24],[4,25,9],[1,134,108],[2,67,43],[2,33,15,2,34,16],[2,33,11,2,34,12],[2,86,68],[4,43,27],[4,43,19],[4,43,15],[2,98,78],[4,49,31],[2,32,14,4,33,15],[4,39,13,1,40,14],[2,121,97],[2,60,38,2,61,39],[4,40,18,2,41,19],[4,40,14,2,41,15],[2,146,116],[3,58,36,2,59,37],[4,36,16,4,37,17],[4,36,12,4,37,13],[2,86,68,2,87,69],[4,69,43,1,70,44],[6,43,19,2,44,20],[6,43,15,2,44,16],[4,101,81],[1,80,50,4,81,51],[4,50,22,4,51,23],[3,36,12,8,37,13],[2,116,92,2,117,93],[6,58,36,2,59,37],[4,46,20,6,47,21],[7,42,14,4,43,15],[4,133,107],[8,59,37,1,60,38],[8,44,20,4,45,21],[12,33,11,4,34,12],[3,145,115,1,146,116],[4,64,40,5,65,41],[11,36,16,5,37,17],[11,36,12,5,37,13],[5,109,87,1,110,88],[5,65,41,5,66,42],[5,54,24,7,55,25],[11,36,12,7,37,13],[5,122,98,1,123,99],[7,73,45,3,74,46],[15,43,19,2,44,20],[3,45,15,13,46,16],[1,135,107,5,136,108],[10,74,46,1,75,47],[1,50,22,15,51,23],[2,42,14,17,43,15],[5,150,120,1,151,121],[9,69,43,4,70,44],[17,50,22,1,51,23],[2,42,14,19,43,15],[3,141,113,4,142,114],[3,70,44,11,71,45],[17,47,21,4,48,22],[9,39,13,16,40,14],[3,135,107,5,136,108],[3,67,41,13,68,42],[15,54,24,5,55,25],[15,43,15,10,44,16],[4,144,116,4,145,117],[17,68,42],[17,50,22,6,51,23],[19,46,16,6,47,17],[2,139,111,7,140,112],[17,74,46],[7,54,24,16,55,25],[34,37,13],[4,151,121,5,152,122],[4,75,47,14,76,48],[11,54,24,14,55,25],[16,45,15,14,46,16],[6,147,117,4,148,118],[6,73,45,14,74,46],[11,54,24,16,55,25],[30,46,16,2,47,17],[8,132,106,4,133,107],[8,75,47,13,76,48],[7,54,24,22,55,25],[22,45,15,13,46,16],[10,142,114,2,143,115],[19,74,46,4,75,47],[28,50,22,6,51,23],[33,46,16,4,47,17],[8,152,122,4,153,123],[22,73,45,3,74,46],[8,53,23,26,54,24],[12,45,15,28,46,16],[3,147,117,10,148,118],[3,73,45,23,74,46],[4,54,24,31,55,25],[11,45,15,31,46,16],[7,146,116,7,147,117],[21,73,45,7,74,46],[1,53,23,37,54,24],[19,45,15,26,46,16],[5,145,115,10,146,116],[19,75,47,10,76,48],[15,54,24,25,55,25],[23,45,15,25,46,16],[13,145,115,3,146,116],[2,74,46,29,75,47],[42,54,24,1,55,25],[23,45,15,28,46,16],[17,145,115],[10,74,46,23,75,47],[10,54,24,35,55,25],[19,45,15,35,46,16],[17,145,115,1,146,116],[14,74,46,21,75,47],[29,54,24,19,55,25],[11,45,15,46,46,16],[13,145,115,6,146,116],[14,74,46,23,75,47],[44,54,24,7,55,25],[59,46,16,1,47,17],[12,151,121,7,152,122],[12,75,47,26,76,48],[39,54,24,14,55,25],[22,45,15,41,46,16],[6,151,121,14,152,122],[6,75,47,34,76,48],[46,54,24,10,55,25],[2,45,15,64,46,16],[17,152,122,4,153,123],[29,74,46,14,75,47],[49,54,24,10,55,25],[24,45,15,46,46,16],[4,152,122,18,153,123],[13,74,46,32,75,47],[48,54,24,14,55,25],[42,45,15,32,46,16],[20,147,117,4,148,118],[40,75,47,7,76,48],[43,54,24,22,55,25],[10,45,15,67,46,16],[19,148,118,6,149,119],[18,75,47,31,76,48],[34,54,24,34,55,25],[20,45,15,61,46,16]],r=function(t,r){var e={};return e.totalCount=t,e.dataCount=r,e},e={};return e.getRSBlocks=function(e,n){var o=function(r,e){switch(e){case g.L:return t[4*(r-1)+0];case g.M:return t[4*(r-1)+1];case g.Q:return t[4*(r-1)+2];case g.H:return t[4*(r-1)+3];default:return}}(e,n);if(void 0===o)throw"bad rs block @ typeNumber:"+e+"/errorCorrectionLevel:"+n;for(var i=o.length/3,a=[],u=0;u<i;u+=1)for(var f=o[3*u+0],c=o[3*u+1],l=o[3*u+2],h=0;h<f;h+=1)a.push(r(c,l));return a},e}(),b=function(){var t=[],r=0,e={getBuffer:function(){return t},getAt:function(r){var e=Math.floor(r/8);return 1==(t[e]>>>7-r%8&1)},put:function(t,r){for(var n=0;n<r;n+=1)e.putBit(1==(t>>>r-n-1&1))},getLengthInBits:function(){return r},putBit:function(e){var n=Math.floor(r/8);t.length<=n&&t.push(0),e&&(t[n]|=128>>>r%8),r+=1}};return e},M=function(t){var r=a,e=t,n={getMode:function(){return r},getLength:function(t){return e.length},write:function(t){for(var r=e,n=0;n+2<r.length;)t.put(o(r.substring(n,n+3)),10),n+=3;n<r.length&&(r.length-n==1?t.put(o(r.substring(n,n+1)),4):r.length-n==2&&t.put(o(r.substring(n,n+2)),7))}},o=function(t){for(var r=0,e=0;e<t.length;e+=1)r=10*r+i(t.charAt(e));return r},i=function(t){if("0"<=t&&t<="9")return t.charCodeAt(0)-"0".charCodeAt(0);throw"illegal char :"+t};return n},x=function(t){var r=u,e=t,n={getMode:function(){return r},getLength:function(t){return e.length},write:function(t){for(var r=e,n=0;n+1<r.length;)t.put(45*o(r.charAt(n))+o(r.charAt(n+1)),11),n+=2;n<r.length&&t.put(o(r.charAt(n)),6)}},o=function(t){if("0"<=t&&t<="9")return t.charCodeAt(0)-"0".charCodeAt(0);if("A"<=t&&t<="Z")return t.charCodeAt(0)-"A".charCodeAt(0)+10;switch(t){case" ":return 36;case"$":return 37;case"%":return 38;case"*":return 39;case"+":return 40;case"-":return 41;case".":return 42;case"/":return 43;case":":return 44;default:throw"illegal char :"+t}};return n},m=function(r){var e=f,n=t.stringToBytes(r),o={getMode:function(){return e},getLength:function(t){return n.length},write:function(t){for(var r=0;r<n.length;r+=1)t.put(n[r],8)}};return o},L=function(r){var e=c,n=t.stringToBytesFuncs.SJIS;if(!n)throw"sjis not supported.";!function(){var t=n("友");if(2!=t.length||38726!=(t[0]<<8|t[1]))throw"sjis not supported."}();var o=n(r),i={getMode:function(){return e},getLength:function(t){return~~(o.length/2)},write:function(t){for(var r=o,e=0;e+1<r.length;){var n=(255&r[e])<<8|255&r[e+1];if(33088<=n&&n<=40956)n-=33088;else{if(!(57408<=n&&n<=60351))throw"illegal char at "+(e+1)+"/"+n;n-=49472}n=192*(n>>>8&255)+(255&n),t.put(n,13),e+=2}if(e<r.length)throw"illegal char at "+(e+1)}};return i},D=function(){var t=[],r={writeByte:function(r){t.push(255&r)},writeShort:function(t){r.writeByte(t),r.writeByte(t>>>8)},writeBytes:function(t,e,n){e=e||0,n=n||t.length;for(var o=0;o<n;o+=1)r.writeByte(t[o+e])},writeString:function(t){for(var e=0;e<t.length;e+=1)r.writeByte(t.charCodeAt(e))},toByteArray:function(){return t},toString:function(){var r="";r+="[";for(var e=0;e<t.length;e+=1)e>0&&(r+=","),r+=t[e];return r+="]"}};return r},S=function(t){var r=t,e=0,n=0,o=0,i={read:function(){for(;o<8;){if(e>=r.length){if(0==o)return-1;throw"unexpected end of file./"+o}var t=r.charAt(e);if(e+=1,"="==t)return o=0,-1;t.match(/^\s$/)||(n=n<<6|a(t.charCodeAt(0)),o+=6)}var i=n>>>o-8&255;return o-=8,i}},a=function(t){if(65<=t&&t<=90)return t-65;if(97<=t&&t<=122)return t-97+26;if(48<=t&&t<=57)return t-48+52;if(43==t)return 62;if(47==t)return 63;throw"c:"+t};return i},I=function(t,r,e){for(var n=function(t,r){var e=t,n=r,o=new Array(t*r),i={setPixel:function(t,r,n){o[r*e+t]=n},write:function(t){t.writeString("GIF87a"),t.writeShort(e),t.writeShort(n),t.writeByte(128),t.writeByte(0),t.writeByte(0),t.writeByte(0),t.writeByte(0),t.writeByte(0),t.writeByte(255),t.writeByte(255),t.writeByte(255),t.writeString(","),t.writeShort(0),t.writeShort(0),t.writeShort(e),t.writeShort(n),t.writeByte(0);var r=a(2);t.writeByte(2);for(var o=0;r.length-o>255;)t.writeByte(255),t.writeBytes(r,o,255),o+=255;t.writeByte(r.length-o),t.writeBytes(r,o,r.length-o),t.writeByte(0),t.writeString(";")}},a=function(t){for(var r=1<<t,e=1+(1<<t),n=t+1,i=u(),a=0;a<r;a+=1)i.add(String.fromCharCode(a));i.add(String.fromCharCode(r)),i.add(String.fromCharCode(e));var f,c,g,l=D(),h=(f=l,c=0,g=0,{write:function(t,r){if(t>>>r!=0)throw"length over";for(;c+r>=8;)f.writeByte(255&(t<<c|g)),r-=8-c,t>>>=8-c,g=0,c=0;g|=t<<c,c+=r},flush:function(){c>0&&f.writeByte(g)}});h.write(r,n);var s=0,v=String.fromCharCode(o[s]);for(s+=1;s<o.length;){var d=String.fromCharCode(o[s]);s+=1,i.contains(v+d)?v+=d:(h.write(i.indexOf(v),n),i.size()<4095&&(i.size()==1<<n&&(n+=1),i.add(v+d)),v=d)}return h.write(i.indexOf(v),n),h.write(e,n),h.flush(),l.toByteArray()},u=function(){var t={},r=0,e={add:function(n){if(e.contains(n))throw"dup key:"+n;t[n]=r,r+=1},size:function(){return r},indexOf:function(r){return t[r]},contains:function(r){return void 0!==t[r]}};return e};return i}(t,r),o=0;o<r;o+=1)for(var i=0;i<t;i+=1)n.setPixel(i,o,e(i,o));var a=D();n.write(a);for(var u=function(){var t=0,r=0,e=0,n="",o={},i=function(t){n+=String.fromCharCode(a(63&t))},a=function(t){if(t<0);else{if(t<26)return 65+t;if(t<52)return t-26+97;if(t<62)return t-52+48;if(62==t)return 43;if(63==t)return 47}throw"n:"+t};return o.writeByte=function(n){for(t=t<<8|255&n,r+=8,e+=1;r>=6;)i(t>>>r-6),r-=6},o.flush=function(){if(r>0&&(i(t<<6-r),t=0,r=0),e%3!=0)for(var o=3-e%3,a=0;a<o;a+=1)n+="="},o.toString=function(){return n},o}(),f=a.toByteArray(),c=0;c<f.length;c+=1)u.writeByte(f[c]);return u.flush(),"data:image/gif;base64,"+u};return t}();qrcode.stringToBytesFuncs["UTF-8"]=function(t){return function(t){for(var r=[],e=0;e<t.length;e++){var n=t.charCodeAt(e);n<128?r.push(n):n<2048?r.push(192|n>>6,128|63&n):n<55296||n>=57344?r.push(224|n>>12,128|n>>6&63,128|63&n):(e++,n=65536+((1023&n)<<10|1023&t.charCodeAt(e)),r.push(240|n>>18,128|n>>12&63,128|n>>6&63,128|63&n))}return r}(t)},function(t){"function"==typeof define&&define.amd?define([],t):"object"==typeof exports&&(module.exports=t())}((function(){return qrcode}));
;(function(){
  var BUILD_TS = 1789177886364;
  var SOURCES = [];
  var CAT_LABELS = {"wechat": "公众号", "ai": "AI 日报", "tech": "科技资讯", "cn_tech": "中文科技", "dev": "开发者", "news": "综合新闻", "podcast": "播客", "youtube": "YouTube"};
  var ANALYSIS_DATA = {"generated_at":"2026-09-12T09:54:30.185496+08:00","keywords":{"global":[],"by_cat":{}},"rising":[],"topics":[{"label":"projects","count":20,"sources":["Google Developers","Tiny Projects"],"links":["https://tinyprojects.dev/posts/tiny_websites_are_great","https://tinyprojects.dev/projects/silicon_valley_domain_names","https://tinyprojects.dev/posts/i_bought_netflix_dot_soy","https://tinyprojects.dev/projects/battle_royale","https://tinyprojects.dev/projects/one_item_store","https://tinyprojects.dev/projects/earlyname","https://tinyprojects.dev/posts/six_months_of_tiny_projects","https://tinyprojects.dev/posts/selling_a_tiny_project","https://tinyprojects.dev/projects/mailoji","https://tinyprojects.dev/posts/selling_tiny_internet_projects_for_fun_and_profit"],"cats":["dev","tech"]},{"label":"developers","count":14,"sources":["Google Developers"],"links":["https://developers.googleblog.com/heygen-x-google-cloud-bringing-avatar-iv-to-tpus/","https://developers.googleblog.com/introducing-credentio-open-source-c-library-for-c2pa-content-credentials-from-google/","https://developers.googleblog.com/why-go-is-an-ideal-language-for-ai-assisted-software-engineering/","https://developers.googleblog.com/mastering-edge-ai-on-raspberry-pi-with-litert-and-gemma/","https://developers.googleblog.com/agent-plugins-package-your-skills-tools-and-more/","https://developers.googleblog.com/scaling-ai-agent-infrastructure-with-the-mcp-stateless-updates/","https://developers.googleblog.com/a-unified-api-for-ai-model-routing/","https://developers.googleblog.com/scaling-real-time-ai-agents-with-session-aware-load-balancing/","https://developers.googleblog.com/enable-on-demand-expertise-with-agent-skills-in-genkit-go/","https://developers.googleblog.com/agent-and-model-evaluations-in-gemini-enterprise-agent-platform-are-now-ga/"],"cats":["tech"]},{"label":"喷嚏图卦","count":4,"sources":["喷嚏网铂程斋"],"links":["https://www.dapenti.com/blog/more.asp?name=xilei&id=195270","https://www.dapenti.com/blog/more.asp?name=xilei&id=195286","https://www.dapenti.com/blog/more.asp?name=xilei&id=195296","https://www.dapenti.com/blog/more.asp?name=xilei&id=195317"],"cats":["news"]},{"label":"铂程的票圈","count":4,"sources":["喷嚏网铂程斋"],"links":["https://www.dapenti.com/blog/more.asp?name=xilei&id=195267","https://www.dapenti.com/blog/more.asp?name=xilei&id=195244","https://www.dapenti.com/blog/more.asp?name=xilei&id=195312","https://www.dapenti.com/blog/more.asp?name=xilei&id=195338"],"cats":["news"]},{"label":"图卦音","count":4,"sources":["喷嚏网铂程斋"],"links":["https://www.dapenti.com/blog/more.asp?name=xilei&id=195263","https://www.dapenti.com/blog/more.asp?name=xilei&id=195240","https://www.dapenti.com/blog/more.asp?name=xilei&id=195306","https://www.dapenti.com/blog/more.asp?name=xilei&id=195329"],"cats":["news"]},{"label":"world","count":2,"sources":["Google Developers"],"links":["https://developers.googleblog.com/how-to-use-google-microbenchmarks-for-evaluating-tpu-performance/"],"cats":["tech"]},{"label":"喷嚏意图","count":2,"sources":["喷嚏网铂程斋"],"links":["https://www.dapenti.com/blog/more.asp?name=xilei&id=195268","https://www.dapenti.com/blog/more.asp?name=xilei&id=195310"],"cats":["news"]},{"label":"七武士：为何赢的是农","count":2,"sources":["喷嚏网铂程斋"],"links":["https://www.dapenti.com/blog/more.asp?name=xilei&id=195247","https://www.dapenti.com/blog/more.asp?name=xilei&id=195308"],"cats":["news"]}],"summary":{"core_trends":"当前数据池呈现低活跃度特征：200份文档仅覆盖8个主题，且跨平台传播值为零。关键词缺失表明内容未形成语义焦点或议题尚未成熟。整体处于信息酝酿的潜伏期，尚未产生显著的社会或市场声量，属于早期微弱信号阶段。","signals":"","rss_insights":"共分析 200 条内容，提取 0 个关键词。","outlook":"建议持续监控文档增长速率与关键词涌现情况。若topic_count突然攀升，可能预示议题进入爆发前夜；否则将长期维持低位静止状态。需结合外部事件触发点评估潜在活跃度拐点。"},"stats":{"total_articles":200,"recent_count":2471,"source_count":502},"quality":{"agihunt_0":85.0,"openai_blog_1":85.0,"google_deepmind_2":0,"google_ai_blog_3":67.5,"arxiv_ai_4":85.0,"arxiv_ml_5":85.0,"arxiv_nlp_6":85.0,"hn_ai_7":85.0,"hn_llm_8":85.0,"google_research_10":42.5,"huggingface_11":45.0,"simonwillison_12":85.0,"codex_rel_15":66.7,"claude_code_rel_16":62.5,"gemini_cli_rel_17":60.0,"mcp_spec_rel_18":0,"mcp_servers_rel_19":0,"aihot_summary_20":65.0,"aihot_full_21":88.7,"aihot_pool_22":85.0,"reddit_ml_103":80.0,"reddit_localllama_104":80.0,"reddit_artificial_105":80.0,"juliaevans_0":0,"overreacted_2":0,"webdev_3":0,"engadget_4":0,"joshcomeau_5":0,"hackernews_6":85.0,"techcrunch_7":84.4,"techcrunchai_7b":85.0,"theverge_8":100.0,"thevergeai_8b":100.0,"wired_10":85.0,"atlasnote_11":75.0,"redisblog_12":62.5,"arxiv_cs_14":85.0,"arstechnica_60":95.3,"mit_tech_review_61":100.0,"krebs_62":0,"thehackernews_63":85.0,"schneier_64":90.0,"github_blog_70":82.5,"github_changelog_71":97.5,"github_copilot_72":90.0,"netflix_tech_73":0,"aws_blog_74":77.5,"cloudflare_blog_75":82.5,"google_dev_76":85.0,"mozilla_hacks_77":0,"vercel_blog_78":65.0,"supabase_blog_79":62.5,"stripe_blog_80":0,"meta_eng_81":0,"美团技术团队_0":98.8,"v2ex_1":57.5,"solidot_3":85.0,"少数派_4":76.7,"爱范儿_5":93.8,"小众软件_8":100.0,"构建被动收入_9":0,"虎嗅_11":85.0,"it之家_13":85.0,"月光博客_15":0,"理想生活实验室_18":62.5,"潮流周刊_21":0,"扯氮集_25":77.5,"deepzz_26":0,"mit科技评论_28":0,"疯投圈_29":0,"超能网_31":85.0,"钛媒体_38":83.5,"人人都是产品经理_39":99.8,"cnbeta_41":85.0,"v2ex技术_44":75.3,"阮一峰的网络日志_0":62.5,"太隐_4":0,"云风的blog_5":77.5,"胡涂说_6":0,"程序员的喵_7":0,"oldjblog_8":0,"randy'sblog_12":0,"卡瓦邦噶_13":77.5,"风雪之隅_14":0,"离别歌_15":0,"hellogithub_17":0,"张鑫旭_18":77.5,"maxos_19":0,"轶哥博客_20":0,"geekplux_21":0,"mactalk池建强_22":0,"xuanwo_23":0,"反斗限免_24":96.5,"halfrost_25":0,"infoq推荐_26":85.0,"二丫讲梵_27":65.0,"唐巧博客_28":0,"baiyun_30":0,"elmagnifico_31":0,"tonybai_33":82.5,"全栈应用开发_36":0,"tinyprojects_37":85.0,"笨方法学写作_38":0,"西秦公子_39":57.5,"涛叔_41":62.5,"小球飞鱼_42":0,"王登科dk_43":0,"小胡子哥_44":98.8,"dbanotes_45":0,"v2ex_all_50":76.2,"v2ex_new_51":74.4,"v2ex_creative_52":79.7,"v2ex_play_53":76.3,"nodeseek_54":72.8,"naixi_55":73.9,"hn_newest_56":85.0,"hn_ask_57":85.0,"hn_show_58":85.0,"linuxdo_latest_59":0,"linuxdo_top_60":0,"linuxdo_posts_61":0,"js_weekly_90":0,"rust_weekly_91":77.5,"golang_weekly_92":62.5,"bytebytego_93":82.5,"reddit_programming_100":80.0,"reddit_webdev_101":80.0,"reddit_selfhosted_102":80.0,"idaily_1":85.0,"中国日报双语_2":67.5,"知乎日报anyfeeder_3":85.0,"法广中文_4":85.0,"bbc中文_5":85.0,"财富中文网_6":81.9,"澎湃新闻_7":82.6,"人民网_8":70.0,"南方周末anyfeeder_9":85.0,"纽约时报中文网_10":85.0,"喷嚏网铂程斋_11":76.0,"雪球热帖_12":100.0,"bbc英语教学_13":77.5,"求是网_14":65.0,"半岛电视台_15":84.5,"CNN_16":81.9,"新华社_17":84.6,"德国之声DW_18":0,"香港01本地_19":65.2,"香港01國際_22":65.0,"朝日新闻_20":66.3,"NHK World_21":0,"42章经_1":0,"三点下班_4":0,"卫诗婕商业漫谈_6":0,"得意忘形_7":0,"起朱楼宴宾客_8":0,"tedradiohour_10":77.5,"人人都是产品经理_0":70.0,"腾讯技术工程_1":60.0,"阿里技术_2":57.5,"阿里云开发者_3":62.5,"大淘宝技术_4":60.0,"新智元_5":77.5,"腾讯云开发者_6":60.0,"前端早读课_7":0,"founder_park_8":57.5,"歸藏的ai工具箱_9":0,"腾讯科技_10":75.0,"infoq_11":85.0,"赛博禅心_12":57.5,"数字生命卡兹克_13":57.5,"十字路口crossing_14":60.0,"极客公园_15":81.9,"京东技术_16":77.5,"web3天空之城_17":0,"ai前线_18":67.5,"51cto技术栈_19":62.5,"稀土掘金技术社区_20":77.5,"dbaplus社群_21":60.0,"深思圈_22":82.5,"海外独角兽_23":57.5,"谷歌开发者_24":70.0,"笔记侠_25":70.0,"月之暗面_kimi_26":60.0,"腾讯研究院_27":70.0,"浮之静_28":70.0,"甲子光年_29":60.0,"z_potentials_30":81.9,"deepseek_31":57.5,"jina_ai_32":0,"datawhale_33":69.2,"向阳乔木推荐看_34":0,"语言即世界language_is_world_35":0,"dify_36":0,"智谱_37":0,"通义实验室_38":0,"百度文心_39":77.5,"腾讯混元_40":0,"智东西_41":67.5,"agent橘_42":62.5,"大模型智能_43":69.2,"ai炼金术_44":0,"ai科技评论_45":67.5,"山行ai_46":0,"土猛的员外_47":0,"deeplearningai_48":62.5,"机器之心sota模型_49":80.0,"阶跃星辰_50":0,"字节跳动seed_51":0,"ai寒武纪_52":60.0,"minimax_稀宇科技_53":0,"花叔_54":62.5,"ainlp_55":75.5,"硅基观察pro_56":60.0,"李继刚_57":0,"沃垠ai_58":60.0,"袋鼠帝ai客栈_59":60.0,"ai科技大本营_60":62.5,"卡尔的ai沃茨_61":60.0,"阿真irene_62":62.5,"优设_63":77.5,"体验进阶_64":0,"超人的电话亭_65":75.8,"clip设计夹_66":0,"ai产品黄叔_67":0,"强少来了_68":0,"小米技术_69":57.5,"哔哩哔哩技术_70":0,"字节跳动技术团队_71":60.0,"滴滴技术_72":57.5,"奇舞精选_73":0,"得物技术_74":80.0,"百度geek说_75":77.5,"前端充电宝_76":0,"qunar技术沙龙_77":0,"vivo互联网技术_78":70.0,"小红书技术redtech_79":57.5,"hellogithub_80":0,"印记中文_81":80.0,"快手技术_82":60.0,"逛逛github_83":60.0,"架构师之路_84":60.0,"硅谷科技评论_85":57.5,"42章经_86":0,"随机小分队_87":57.5,"阿里研究院_88":57.5,"创业邦_89":80.7,"csdn_90":65.0,"吴晓波频道_91":70.0,"投资实习所_92":0,"经纬创投_93":65.0,"少数派_94":67.5,"网易科技_95":62.5,"硅谷101_96":57.5,"真格基金_97":62.5,"深网腾讯新闻_98":60.0,"白鲸出海_99":65.0,"硅星人pro_100":77.5,"暗涌waves_101":57.5,"夕小瑶科技说_102":60.0,"l先生说_103":57.5,"有新newin_104":82.5,"晚点latepost_105":62.5,"刘润_106":75.0,"刘小排r_107":0,"机器之心_108":70.0,"魔搭modelscope社区_109":82.5,"43_talks_110":57.5,"言午_111":0,"思特沃克洞见_112":0,"数据可视化_antv_113":0,"晚点再听latercast_114":82.5,"古典古少侠_115":0,"ai异类弗兰克_116":60.0,"ai产品阿颖_117":62.5,"阑夕_118":62.5,"pm圈子_119":76.7,"哈佛商业评论_120":65.0,"paperagent_121":67.5,"有赞coder_122":0,"draco正在vibecoding_123":57.5,"36氪_124":80.2,"36氪官网_376":85.0,"playwright实战教程_125":57.5,"华尔街见闻_126":80.0,"青稞ai_127":85.0,"ai闲谈_128":0,"罗西的思考_129":57.5,"武志红_130":80.0,"槽边往事_131":75.8,"人物_132":67.5,"猫笔刀_133":62.5,"周国平_134":70.0,"南方周末_135":80.0,"财新_136":84.4,"三联生活周刊_137":82.1,"一席_138":57.5,"xiaomi_mimo_139":0,"钉钉_140":62.5,"飞书_141":0,"携程技术_142":0,"蚂蚁技术anttech_143":57.5,"爱奇艺技术产品团队_144":77.5,"丁香医生_145":80.0,"saas白夜行_146":60.0,"世界银行_147":70.0,"老俞闲话_148":57.5,"小林coding_149":65.0,"斯坦福社会创新评论_150":57.5,"谷雨实验室_151":57.5,"每日豆瓣_152":75.0,"新周刊_153":80.9,"果壳_154":80.0,"knowyourself_155":80.0,"凤凰网财经_156":80.0,"凤凰网_157":79.7,"雪球_158":77.5,"财联社_159":80.0,"张佳玮写字的地方_160":62.5,"投资界_161":80.0,"央视财经_162":80.0,"支付宝体验科技_163":0,"秋芝2046_164":0,"吴鲁加_165":0,"香帅的金融江湖_166":75.5,"效率火箭_167":0,"高可用架构_168":0,"腾讯云中间件_169":57.5,"虎嗅app_170":80.0,"雷峰网_171":83.1,"钛媒体_172":79.7,"paperweekly_173":65.0,"智能涌现_174":57.5,"飞哥说ai_175":0,"水木人工智能学堂_176":57.5,"从码农到工匠_177":0,"快刀青衣_178":57.5,"hellosreagent_179":0,"mactalk_180":62.5,"刘言飞语_181":0,"产品二姐_182":57.5,"ai大模型应用实践_183":0,"王吉伟_184":57.5,"风叔云_185":0,"脑极体_186":60.0,"麦肯锡_187":70.0,"麻省理工科技评论app_188":69.2,"砺石商业评论_189":71.5,"通往agi之路_190":0,"小互ai_191":57.5,"喔家archiself_192":0,"乱翻书_193":77.5,"见实_194":89.1,"zartbot_195":0,"产品犬舍_196":0,"字节跳动开源_197":0,"二一的笔记_198":0,"一泽eze_199":0,"前端开发爱好者_200":60.0,"南京发布_201":80.0,"网信中国_202":80.0,"网信北京_203":80.0,"公安部网安局_204":80.0,"方伟看十年_205":57.5,"写代码的宝哥_206":62.5,"phodal_207":77.5,"毛有话说_208":0,"nov心理_209":75.8,"泽平宏观_210":77.5,"峰瑞资本_211":0,"高瓴时间_212":0,"高瓴创投_213":0,"聪明投资者_214":60.0,"中金点睛_215":75.0,"也谈钱_216":57.5,"山行资本_217":60.0,"格隆汇app_218":80.0,"棱镜_219":77.5,"海豚研究_220":65.0,"经济观察报_221":88.6,"21世纪经济报道_222":80.0,"老钱说钱_223":0,"老钱日日谈_224":0,"东方财富网_225":80.0,"郑立涛_226":0,"佳芮的创业笔记_227":0,"财经早餐_228":70.0,"中国新闻周刊_229":80.0,"第一财经_230":80.0,"券商中国_231":80.0,"单读_232":60.0,"艾逗笔_233":0,"腾讯nba_234":0,"苏群_235":77.5,"篮球先锋报_236":65.0,"杨毅侃球_237":72.5,"懂球娘娘_238":72.5,"足球报_239":80.0,"体坛周报_240":75.0,"澎湃运动家_241":62.5,"五星体育_242":81.2,"天下足球_243":60.0,"央视网体育_244":62.5,"央视新闻_245":80.0,"环球时报_246":80.0,"新华社_247":80.0,"每日经济新闻_248":80.0,"腾讯财经_249":61.3,"乒乓世界_250":60.0,"南风窗_251":80.0,"央广网_252":80.0,"科普中国_253":80.0,"网球之家_254":86.0,"晚点对话_255":0,"aibase基地_256":62.5,"非凡产研_257":84.2,"晚点ai_258":0,"洞见_259":80.0,"十点读书_260":80.0,"人民日报_261":80.0,"央视网_262":80.0,"跑步指南_263":0,"生命时报_264":75.0,"梅斯医学_265":80.0,"cctv生活圈_266":70.0,"每晚一卷书_267":79.7,"看理想_268":67.5,"罗辑思维_269":65.0,"叶檀财经_270":57.5,"张湧说财经_271":60.0,"wind万得_272":65.0,"功夫财经_273":70.0,"混知_274":62.5,"科技美学_275":81.8,"心智工具箱_276":0,"iamsujie_277":60.0,"一条_278":77.5,"中国国家地理_279":75.0,"混沌学园_280":62.5,"携隐melody_281":60.0,"集智俱乐部_282":77.5,"格兰投研_283":62.5,"区块链头条_284":62.5,"转转技术_285":0,"陈鲁豫的电影沙发_286":0,"半导体行业观察_287":95.0,"饭统戴老板_288":60.0,"远川研究所_289":60.0,"caoz的梦呓_290":57.5,"孤独大脑_291":62.5,"孟岩_292":57.5,"appso_293":80.0,"i食色摇闲情_294":82.5,"地球知识局_295":70.0,"星球研究所_296":57.5,"利维坦_297":57.5,"小众消息_298":0,"互联网怪盗团_299":0,"九边_300":60.0,"知识分子_301":60.0,"deeptech深科技_302":65.0,"warfalcon_303":77.5,"investguru_304":0,"环球科学_305":75.0,"廖信忠_306":0,"大力如山_307":0,"新京报书评周刊_308":80.0,"老张投研_309":60.0,"心木微笔_310":60.0,"知乎日报_311":70.0,"真实故事计划_312":57.5,"刘备教授_313":62.5,"理想国imaginist_314":67.5,"智族life_315":57.5,"神经现实_316":60.0,"中科院物理所_317":81.7,"六神磊磊读金庸_318":57.5,"思想钢印_319":57.5,"智族lab_320":62.5,"原理_321":62.5,"标志情报局_322":70.0,"游戏研究社_323":72.5,"王建硕_324":0,"返朴_325":65.0,"澎湃新闻_326":80.0,"读者_327":80.0,"半月谈_328":80.0,"国家人文历史_329":62.5,"人民日报评论_330":82.5,"人民网_331":80.0,"范冰的二次学习_332":57.5,"南方人物周刊_333":70.0,"正和岛_334":70.0,"界面新闻_335":82.3,"浪潮工作室_336":67.5,"pricetag发现好应用_337":62.5,"红杉汇_338":57.5,"银行螺丝钉_339":77.5,"集思录_340":65.0,"etf进化论_341":62.5,"阿虚同学_342":62.5,"虹膜_343":70.0,"环球设计_344":62.5,"日本设计小站_345":67.5,"memm设计知识分享_346":57.5,"设计癖_347":80.0,"淘宝设计_348":0,"独立鱼电影_349":60.0,"澎湃思想市场_350":69.2,"游戏葡萄_351":65.0,"后浪研究所_352":69.2,"太阳照常升起_353":0,"githubdaily_354":60.0,"githubstore_355":82.5,"一天一篇经济学人_356":76.8,"财经杂志_357":83.9,"得到_358":0,"帆书樊登讲书_359":80.0,"中国金融四十人论坛_360":62.5,"barrons巴伦_361":73.3,"新榜_362":70.0,"运营研究社_363":75.0,"窄播_364":62.5,"界面文化_365":0,"design360_366":62.5,"brand的好奇心_367":62.5,"企鹅吃喝指南_368":65.0,"wallpaper中文版_369":62.5,"工业设计_370":70.0,"点拾投资_371":0,"三折人生_372":0,"小lin说的公众号_373":0,"刀法研究所_374":70.0,"张小珺jùn｜商业访谈录_0":0,"罗永浩的十字路口_1":0,"屠龙之术_2":0,"42章经_3":0,"硬地骇客_4":0,"硅谷101_5":0,"半拿铁_|_商业沉浮录_6":62.5,"开始连接_linkstart_7":62.5,"高能量_8":0,"此话当真_9":0,"牛油果烤面包_10":0,"晚点聊_latetalk_11":0,"乱翻书_12":0,"tianyu2fm_—_对谈未知领域_13":0,"声动早咖啡_14":65.0,"科技乱炖_15":0,"what's_next｜科技早知道_16":62.5,"声东击西_17":62.5,"疯投圈_18":0,"商业就是这样_19":62.5,"枫言枫语_20":62.5,"保持偏见_21":0,"三五环_22":62.5,"皮蛋漫游记_23":0,"ai炼金术_24":0,"十字路口crossing_25":0,"信号与噪声_26":0,"人民公园说ai_27":0,"跨国串门儿计划_28":70.0,"知行小酒馆_29":62.5,"搞钱女孩_30":62.5,"起朱楼宴宾客_31":0,"面基_32":0,"第一财经_33":67.5,"无人知晓_34":0,"纵横四海_35":0,"自我进化论_36":0,"自习室_study_room_37":0,"慢速生长_38":0,"诗梳风_39":62.5,"谭立人_40":0,"李诞_41":0,"岩中花述_42":0,"蒋方舟·一寸_43":0,"游荡集_44":62.5,"一席_45":62.5,"独树不成林_46":0,"文化有限_47":0,"忽左忽右_48":62.5,"梁永安的播客_49":0,"看理想圆桌_50":62.5,"不合时宜_51":0,"天真不天真_52":0,"凹凸电波_53":0,"随机波动stochasticvolatility_54":0,"东腔西调_55":62.5,"东亚观察局_56":62.5,"肥话连篇_57":0,"捕蛇者说_58":0,"卫诗婕｜漫谈light_the_star_59":0,"ai_engineer_0":65.0,"ai_explained_1":0,"ai_master_2":65.0,"ai_search_3":45.0,"ai_video_school_4":47.5,"aicodeking_5":55.0,"andrej_karpathy_6":0,"anthropic_7":0,"assemblyai_8":45.0,"claude_9":47.5,"cognitive_revolution_10":50.0,"deeplearningai_11":0,"every_12":0,"futurepedia_13":52.5,"google_deepmind_14":45.0,"how_i_ai_15":47.5,"hung-yi_lee_16":0,"langchain_17":57.5,"last_week_in_ai_18":50.0,"liam_ottley_19":47.5,"machine_learning_street_talk_20":50.0,"matt_wolfe_21":57.5,"mattvidpro_ai_22":45.0,"matthew_berman_23":65.0,"networkchuck_24":50.0,"nick_saraev_25":42.5,"no_priors_26":47.5,"openai_27":65.0,"pika_labs_28":42.5,"riley_brown_29":52.5,"runway_30":47.5,"siraj_raval_31":42.5,"tao_prompts_32":0,"the_ai_advantage_33":65.0,"tina_huang_34":0,"two_minute_papers_35":47.5,"unsupervised_learning:_redpoin_36":0,"wes_roth_37":52.5,"yannic_kilcher_38":42.5,"leerob_39":0,"跟李沐学ai_40":0,"acquired_41":0,"alex_kantrowitz_42":52.5,"all-in_podcast_43":50.0,"better_ideas_44":0,"branch_education_45":0,"business_insider_46":65.0,"coldfusion_47":50.0,"core_memory_podcast_48":57.5,"crashcourse_49":45.0,"curious_refuge_50":42.5,"dwarkesh_patel_51":52.5,"eo_52":0,"google_53":42.5,"greg_isenberg_54":50.0,"invest_like_the_best_55":50.0,"kurzgesagt_-_in_a_nutshell_56":55.0,"lex_fridman_57":0,"luma_58":47.5,"my_first_million_59":60.0,"naval_60":0,"nikhil_kamath_61":65.0,"sabin_civil_engineering_62":0,"silicon_valley_girl_63":55.0,"statquest_with_josh_starmer_64":0,"stripe_65":42.5,"the_diary_of_a_ceo_66":65.0,"the_knowledge_project_podcast_67":50.0,"the_primetime_68":62.5,"theoretically_media_69":42.5,"this_week_in_startups_70":50.0,"thomas_frank_71":0,"y_combinator_72":47.5,"a16z_73":57.5,"companyman_74":0,"mrblock_區塊先生_75":60.0,"struthless_76":0,"patrick_boyle_77":0,"sequoia_capital_78":42.5,"andrew_huberman_79":65.0,"chris_williamson_80":65.0,"mrbeast_81":60.0,"national_geographic_82":62.5,"powerfuljre_83":45.0,"smartereveryday_84":0,"white_cube_youtube_85":45.0,"一席_86":42.5,"一条_87":42.5,"ted_88":60.0,"aj&smart_89":0,"designcourse_90":0,"designerup_91":45.0,"figma_92":52.5,"first_of_kind_93":0,"flux_academy_94":47.5,"lenny's_podcast_95":65.0,"mind_the_product_96":55.0,"nngroup_97":45.0,"product_school_98":47.5,"the_futur_99":45.0,"yobi321_100":0,"3blue1brown_101":0,"ali_abdaal_102":47.5,"anthony_vicino_103":0,"justin_sung_104":0,"matt_d'avella_105":0,"minutephysics_106":0,"李永乐老师_107":42.5,"amigoscode_108":42.5,"beyond_coding_109":47.5,"bytebytego_110":0,"computerphile_111":45.0,"fireship_112":50.0,"github_113":60.0,"hussein_nasser_114":42.5,"modern_software_engineering_115":47.5,"real_engineering_116":42.5,"ryan_peterman_117":65.0,"spring_i_o_118":0,"the_pragmatic_engineer_119":50.0,"theo_-_t3․gg_120":52.5,"traversy_media_121":0,"web_dev_simplified_122":42.5,"freecodecamp.org_123":45.0},"hot_trends":{"weibo":{"网红铁头退庭时辱骂法庭":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"举报考古文物失踪后店铺遭轮番查":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"我国发现世界级规模深海矿床":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"领完证大街上碰到都认不出来":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"曝丁禹兮卢昱晓新剧延期开机":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"宁波大学开学典礼突降暴雨校长只讲3句话":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"熬夜的伤害通过睡觉能补回来吗":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"16个月女婴吞纽扣电池食道严重腐烂":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"兰香如故昔日未婚妻变婢女":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"治理龟速开车":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"马斯克怒了":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"兰香如故观众反响":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"法考":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"高考数学132分 开学考只考了12分":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"西电学生回应数学开学考":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"从瑞金到延安的初心奔赴":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"女孩去邻居家吃饭惨遭夫妻分尸":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"张家齐的日常支出太吓人了":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"这段话杀死了内耗型人格":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"女子与局长亲密勒索不成告强奸未遂":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"女子向大雁塔景区雨水井塞不明物":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"荣耀Magic9ProMax苔青色":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"栾念尚之桃重逢擦肩而过":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"早春晴朗大结局":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"服贸会今日开幕":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"复方甘草片 低钾血":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"硬座出差 软裁员":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"一只羊脱衣全过程":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"网传虞书欣连开三部":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"栾念尚之桃结局":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"梅姨被抓捕完整经过":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"美网仅剩郑钦文与前五种子":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"有了低保就一定要活成穷人样子么":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"栾念求婚成功":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"梅姨在广州摆摊卖切块芒果":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"张本美和说目标是包揽亚运4金":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"苹果折叠屏 iPhone Duo":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"高一女生被教官猥亵老师说没多大事":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"黄友政2比3贾哈":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"柯淳演电影了":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"司美格鲁肽背后的女人":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"iPhone Duo":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"余宇涵身体不适演唱会延期":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"Duo 手机iPad二合一":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"自费买可乐的外卖骑手被奖励一年骑手餐":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"三十而已被裁掉合照的顾佳":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"栾念尚之桃穿得太少了":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"duo是什么意思":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"美网男单18年无人能卫冕":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"女孩狂喝椰子水汇报工作时突然晕厥":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"付磊婚姻不对等":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"宁德时代宜宾基地回应":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"iPhone18系列":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"司美格鲁肽有5大副作用":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"人民日报锐评一边高消费一边领低保":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"西安大雁塔投物女子已被警方找到":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"宁德时代已报警":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"内蒙古锡林郭勒地震":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"曾辉录披哥胖了11斤":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"小米澎程攻防需求误发":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"王者万象棋首支职业战队成立":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"苹果Duo怎么读":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"梅姨微信朋友圈曝光":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"河南地震":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"戚薇AI脸演丧尸片了":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"迪丽热巴老式脸盆帽子":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"梅姨证件照曝光":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"白鹿常华森吻戏好苏":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"一转眼iPhone都成年了":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"梅姨":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"早春晴朗杀疯了":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"康康爷爷睡梦中离世":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"感受长征出发前的峥嵘岁月":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"iPhone18Pro小号灵动岛":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"捐赠人回应被资助女孩质问没打生活费":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"被指摸臀4岁男孩已正常返校上学":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"国乒今日三战三负":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"韩莹回应战胜蒯曼":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"郑钦文vs莱巴金娜":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"被取消资助女生愿换掉苹果手机":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"柬埔寨一诈骗园区内部曝光":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"苹果新CEO发布会前更新动态":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"苹果发布会":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"刘恋想问早春晴朗作者自己是不是原型":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"詹俊预测郑钦文莱巴金娜将战决胜盘":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"早春晴朗好大方的花絮":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"一图速览2026年服贸会":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"iPhone18Pro价格":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"苹果 涨价":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"iPhone18Pro 勃艮第红":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"郑钦文4比3莱巴金娜":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"iPhone18ProMax可变光圈稳了":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"中国女篮vs波多黎各女篮":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"iPhoneDuo 屏下摄像头":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"iPhoneDuo价格":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"iPhone18Pro颜色":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"AirPods5 便宜":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"郑钦文美网止步八强":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"苹果回应iPhoneDuo是否有折痕":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"郑钦文美网1比2莱巴金娜":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"教师节":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"iPhoneDuo过渡动画 完美":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"郑钦文回应无缘美网四强":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"心动的信号":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"刘翔回应安置进展":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"2026最美教师":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"三星嘲讽苹果iPhoneDuo":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"司美格鲁肽":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"警方通报鲜花饼吐痰事件":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"井柏然孙千花絮比正片还甜":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"被资助女生浓妆艳抹停助后遭威胁曝光":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"iPhone17涨价":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"青春华章":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"华为折叠屏":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"无折痕":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"日本梅毒男性20到60岁女性20左右":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"小米折叠屏":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"人类史上首次老人比小孩多":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"iPhoneDuo 折痕":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"iPhone18Pro颜色 男士内裤":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"梅姨首任丈夫称她生两个儿子后离开":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"刘翔名下体育公司已注销":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"兰香如故14首OST":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"长大后才发现好老师的真相":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"上海市体育局通报刘翔安置问题":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"徐艺洋时隔一个月再夺冠":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"花少第一期你怎么看":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"刘翔工资卡11年0支出":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"邓为都快急死了张晚意还在松弛":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"梅姨出摊卖芒果影像":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"Wayward道歉":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"富二代晒家业评论区全在问双休":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"Only Apple Can Duo":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"中国继续保持双向投资大国地位":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"罗永浩吐槽iPhoneDuo多处抄袭":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"恋综女嘉宾自曝离过婚":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"教师节礼物在校门口被集体拦截":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"建议大家把内裤袜子丢洗衣机洗":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"早春晴朗云合":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"梅姨儿子称3岁被抛弃很恼火":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"上海市体育局发布情况通报":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"独家对话梅姨儿媳":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"青岛货轮火灾造成重大人员伤亡":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"女生自曝没考到年级前6被资助人拉黑":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"苹果CEO 张铁牛":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"青岛货轮火灾":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"人一旦拥有了电车":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"罗永浩接连炮轰苹果":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"青岛货轮火灾现场图":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"青岛货轮火灾已致20人死亡":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"日本梅毒暴发与三个一有关":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"女生咨询能否起诉停捐者网友怒了":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"青岛起火外籍货轮上共42人":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"早春晴朗2026第二部云合破40%的剧":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"教师节发祝福被删":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"青岛货轮火灾25人遇难":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"我国成功发射一箭六星":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"赵昭仪录节目突发哮喘":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"8部云合破40%的剧":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"IU新歌献给刘仁娜":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"花少8全员有嘴":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"教育界迎来了最严厉的父母":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"孙怡被说妆前一个人妆后一个人":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"iPhone17Pro线下降价":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"中国女篮VS法国女篮":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"上海28元一份馄饨只有两颗":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"人为什么要读书最好的答案":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"花少8一分钟就把选房解决了":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"华为Mate90 定价":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"舍不得十岁老狗放弃更好大学":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"女子独自骑马去新疆遇大爷骚扰":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"三星回应多邻国开撕":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"2岁女孩逛故宫指着文物让爸爸买":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"感情真的会跟着环境走":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"10天不吃糖身体变化有多大":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"曼联vs沙巴巴库":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"多邻国 iPhone的duo是我的多":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"拜仁5比0大胜博德闪耀":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"4次考公失败后花2万2旅行6国":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"iPhone18Pro全球售价对比":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"早春晴朗短剧版":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"重庆14女生被殴打7人被拘":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"美联储9月加息概率":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"女孩被包办婚姻逃离后父母跨省抓人":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"花少8钱多不累还有手机":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"丁俊晖晋级英格兰赛8强":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"双休购小程序因违规暂停服务":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"油价":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"景德镇学院通报宿舍调整事件":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"库克承认是看华为等厂家出折叠机才出的":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"杭州一阿里员工被派去看苹果发布会":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"梅姨正脸":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"A股":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"服贸会带你解锁消费服务新图景":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"我还在用正太苹果":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"网传时团七周年演唱会取消":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"邻居表示梅姨儿子20多岁是个傻儿子":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"车主称坠楼砸车小孩家长态度转变":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"苹果价格把我的购物欲治好了":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"江西台记者采访遭殴打":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"燃油车卖不动了加油站怎么办":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"A股又调整":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"冬城猎凶 好看":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"萨巴伦卡莱巴金娜美网争冠":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"iPhone17Pro史上最低价":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"辽E点看法":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"洪水中被蛇咬身亡女子家属起诉养殖户":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"李现李一桐剧宣":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"库克 华为":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"复刻栾念的家":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"我国深海科考新突破":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"井柏然 现偶整不动了":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"网易 鸿蒙":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"第一批用阿福的人瘦了500万斤":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"携程垄断被罚51亿后又现房价刺客":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"谭松韵人缘":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"ModelYP 小米YU7GT":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"赴山海删减片段":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"花少8":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"警方通报江西台记者采访被打":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"女子凭支付信息瑜珍2确认是梅姨":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"周启豪3比1贾哈":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"男子离婚6年后发现自己被去父留子":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"T1冲击LCK决赛":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"雷宇扬去世":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"香蕉地喷3天农药毒死隔壁5万斤牛蛙":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"服贸会上一眼未来":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"中国汽车全球首次使用折叠屏":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"白敬亭谭松韵一个叫姐一个叫哥":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"银河左岸音乐节公告":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"艾特孙千结果井柏然回复了":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"葫芦爷爷重新挂出葫芦":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"油价12日起上调":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"姚月茂抖音账号被禁止关注":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"大幅上调日本公民赴华签证规费":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"男子编造停捐遭威胁事件被抓":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"男子离婚6年后才知孩子改随母姓":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"男子停止助学资助反被威胁事件反转":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"7岁半性早熟女童家里是开炸鸡店的":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"资助女生被威胁系男子自导自演":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"iPhoneDuo图标三合一引争议":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0}},"zhihu":{"打假网红铁头敲诈勒索案一审被判八年，伙同他人威胁曝黑料，向带货主播索要数百克黄金，哪些信息值得关注？":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"普通人抱着「关你屁事，关我屁事」的态度生活，究竟会让自己越活越轻松，还是越活越艰难？":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"医生建议大家把内裤袜子放洗衣机洗，称会更干净，真的是这样吗？​不会造成交叉污染吗？":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"如何看待华为麒麟芯片 9050pro？":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"湖南小学生梦游坠楼砸中宝马车定损近 5 万元，家长从主动赔偿转为用拆车件维修并删视频，你怎么看这种转变？":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"中国驻日本大使馆调整对日签证规费，外交部表示是根据对等的原则作出的安排，哪些信息值得关注？":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"官方通报「男子称停止资助后遭受助学生质问催捐」为假消息，媒体曝该男子已被刑拘，哪些信息值得关注？":{"trend":"falling","curr_rank":7,"prev_rank":1,"rise":-6,"duration":4},"为什么打到现在，伊朗还有能力反击美国？":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"月之暗面 Kimi K2.8 Preview 模型 9 月 11 日上线 kimi code，如何评价其表现？":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"如果孩子这辈子注定考不上 985/211，只能做个普通体力劳动者，那我拼命鸡娃，买学区房的意义是什么？":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"刘禹锡也很乐观，为什么在「乐观」这方面不如苏轼有代表性？":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"「双休购」小程序走红，买东西可选双休的企业下单，反映出什么社会需求？这样的消费风潮可能如何影响市场？":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"怎么看 DeepSeek Flash 系列 9 月 10 日将再调整定价，除输出外回归 8 月 17 日前价格？":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"香港首任特首董建华逝世，享年 89 岁，他有哪些贡献值得铭记？":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"太子奶创始人李途纯去世，曾以 8888 万夺央视「标王」，被拘禁 15 个月后获无罪释放，如何评价他的一生？":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"孙悟空大闹天宫时，如来佛祖为什么那么听话，玉帝一 「 传旨 」 他就来？":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"如何看待 Buckmaster 披露 OpenAI 在 NS 方程突破中的学术掠夺与威胁言论？":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"OpenAI 宣布攻克了 N-S equations 这一千禧年问题，这意味着什么？会产生哪些影响？":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"网友称自己上班时突然不认识字了，连数字也不认识了，这是咋回事？能认定为工伤吗？":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"11 月 1 日起企业向个人付款要代扣增值税了，自由职业者和企业主分别需要注意什么？":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"《欢迎来龙餐馆》为什么袭击的时候偏偏留了老扎一命？":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"沈阳马拉松赛后一次性纸杯遍地，市体育局称「是普遍现象，已全面清扫」，这是不可避免的吗？有没有替代方案？":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"「甲醛风波」后康保白菜收购价跌至三分之一，全县紧急自救，网格员监督采收、菜农生吃白菜，能挽回信任吗？":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"发烧时明明体温在升高，人为什么反而会冷得发抖？":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"如何看待高考数学 132 分的学生在西电数学开学考只考 12 分，33 分竟位列前 6%？大学入学考是在考察什么？":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"宁德时代股价大跌，为啥有人说是小米汽车推出龙甲电池导致的？未来「去宁德化」会不会成为车企的一种趋势？":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"8 月新能源车零售 100.5 万辆，同比下降 10.1%，燃油车零售 54 万辆，同比下降 40%，如何解读？":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"为什么感觉台湾的卤肉饭远没有大陆的「台湾卤肉饭」好吃，这中间差异在哪里？":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"为什么近代西方推理小说在设计军人形象时总喜欢把军衔设定为上校?":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"宁夏一高校宿舍配冰箱、智能马桶和密码锁，设施堪比星级酒店，高校为何开始试水高配宿舍？会成为趋势吗？":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"黑龙江一次撤销 32 人次运动员技术等级称号，均涉省乒乓球锦标赛，具体是怎么回事？":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"星宇股份已获港股上市备案却三周仍无聆讯日程，受此次裁员风波影响有多大？会影响公司上市吗？":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"很多人认为本地部署一个大模型，就实现 token 自由，就可以干活了，真的吗？":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"南阳「老头乐」被禁止上路，怎样看待这一规定？该如何平衡老年人出行需求与交通安全？":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"如何看待曝某厂不让普工上厕所致拉裤兜，致其车间裸奔并拿粪便扔向班长，宁德时代宜宾基地回应称不是本公司？":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"网友称欧洲西瓜硬到要用锯子切，为啥西瓜看起来这么硬？跟我们种的西瓜有啥区别吗？":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"如何看待曝某厂不让普工上厕所致拉裤兜，致其车间裸奔并拿粪便扔向他人，宁德时代宜宾基地回应称不是本公司？":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"如何评价 DeepSeek V4.1 Flash 将于 2026 年 9 月 10 日上线，以及 V4Pro 下架？":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"苹果首款折叠屏 iPhone 爆料起售价 2199 美元，人民币近 1.5 万元，如何看待该定价？":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"男子看望奶奶时因桥梁破损坠亡，9 天后奶奶也因受打击离世，死者父母获赔 120 万，从法律角度如何解读？":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"如何看待 2026 年 9 月 9 日 deepseek 官网公告将 v4pro 统一路由至 v4.1flash？":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"OpenAI 首席科学家称已造出「异星心智」，并警告「全人类都要刹车」，这意味着什么？":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"宁夏 7 人假意应聘，借居住条件差等理由「软暴力」向工方勒索共 16 起，最高被判七年，如何从法律角度解读？":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"C919 在 2026 年 1 月和 8 月再次出现「零交付」，这背后可能有哪些原因？":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"如何评价番茄小说最新的全勤新规定？":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"青藏高原地底是否有巨型矿床？":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"郑钦文从排名跌到一百名开外到如今一路挺进美网八强，你认为她的状态算重回巅峰了吗？":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"梅姨在广州城中村落网，住五百元 / 月的十平米出租屋，摆摊卖芒果为生，高 1.5 米左右，哪些细节值得关注？":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"如何评价 2026 苹果秋季发布会？哪些亮点值得关注？":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"宇树科技发布视频称，首次实现人形机器人全自主搏击，这一进展意味着什么？":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"如何评价二路解说 Wayward 在解说 IG vs LGD 时质疑涉及「假赛」？二路整活的边界在哪里？":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"人到什么年龄就开始老花眼了？":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"青藏高原及周边地区 50 年冰储量已减少 20%，冰川冰崩将变得常态化，这意味着什么？":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"为什么电脑重启之后，很多奇怪的问题真的会消失？":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"如何评价苹果折叠屏手机 iPhone Duo？国行售价 15999 元起值得入手吗？":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"2026 女篮世界杯八强附加赛，中国女篮 75：72 战胜波多黎各女篮晋级八强，如何评价本场比赛？":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"郑钦文 1-2 不敌莱巴金娜，止步美网八强，如何评价本场比赛？":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"成吉思汗家族的继承者为什么从窝阔台系转到了拖雷系?":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"成为老师以后，你发现这份工作和入行前想象中最不一样的地方是什么？":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"iPhone 18 Pro 系列 9999 元起，最高售价 20499 元，此次升级能撑起这次涨价吗？":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"霸王茶姬在上海试卖茶叶蛋，单价 5 元，搭配奶茶半价，为何瞄准早餐市场？你愿意下单吗？":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"今年前 8 个月我国货物贸易进出口总值 34.78 万亿元，同比增长 17.6%，如何解读这一数据？":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"如何看待勇哥餐饮被指维护让员工干 17 个小时的老板？":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"如何看待大二学生因用名牌手机被取消资助后威胁要曝光，现愿意更换手机、到资助者亲戚家的店里打工挣钱？":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"为什么成龙的 8 分动作片有 12 亿票房，而周星驰的 6 分喜剧片却有 23 亿票房？是喜剧片市场远大于动作片吗？":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"维密一员工称请假陪患癌母亲做手术遭拒，提出辞职领导却马上批准，如何看待此事？遇到公司拒假该怎么办？":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"如何评价刘翔发言「我希望组织认真考虑每一位运动员的出路…他们搭上整个青春健康，甚至留下永久的伤病」？":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"如何评价游戏《绝区零》的人物建模？":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"如何评价霍奇猜想（七大千禧难题之一）疑似被 OpenAI 解决？":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"上海体育局称向刘翔提供田径中心负责人、体育高校等安置方向，刘翔最终选择自主择业，怎样看待刘翔的选择？":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"酒店为什么会有三小时钟点房？":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"荷马《奥德赛》中 12 名女奴被处死的情节，为什么被诺兰删掉了？这一改编有什么用意？":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"为什么身为成年人的我，基本功嘎嘎结实，游泳却只能游 25 米就游不动了？":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"《我的前半生》为何那么会算计的凌玲，两段婚姻都失败了？":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"山东青岛市北海造船有限公司一艘外籍货轮靠港维修期间起火，造成重大人员伤亡，目前情况如何？":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"如何评价正式发布的 DeepSeek V4.1 Flash？":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"山东青岛市北海造船有限公司一艘外籍货轮靠港维修期间起火，已造成 20 人遇难，目前情况如何？":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"白人饭的魅力主要是省时还是健康？":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"云南昆明警方通报「因工资低往鲜花饼里吐痰」，造谣者已被行拘，这类为博流量编造谣言的现象为何屡屡发生？":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"《王者荣耀》衍生作《王者万象棋》9 月 10 号全平台公测，你的游玩体验如何？":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"韩国指控长鑫盗窃三星工艺，国产内存份额达 10%，知识产权纠纷会如何影响其发展？":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"如何看待 Anthropic 研究员 Jacob 离职，称 AI 公司正「拿全人类的命运下注」？":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"既然 AI 一分钟就能开发出像《开心消消乐》《植物大战僵尸》这样的游戏，为什么排行榜上还是这些老游戏？":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"我不明白中国网球一姐郑钦文，为啥前段时间状态低迷，这次美网她就如换了一个人似的？":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"如何看待福耀科技大学首届 50 名本科生，暑期 13 人赴剑桥交流 19 人大厂实习？高资源小规模办学价值怎么样？":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"山东青岛北海造船厂一货轮火灾事故已造成 25 人遇难":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"女子旧手机号二次放号后支付宝被哈啰盗刷 6551 元，平台仅补 200 元，这合理吗？暴露了哪些问题？":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"2026 女篮世界杯 1/4 决赛，中国女篮 61 比 90 不敌法国女篮，止步八强，如何评价本场比赛？":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"数学已经被 AI 彻底革命了么？":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"浦东机场出租车司机以「车坏了」、「提前付钱」为由甩客，乱象背后原因是什么？":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"我看《明朝那些事儿》，发现宦官这个字眼尤为频繁，但唯独少了外戚，请问外戚去哪里了？":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"如何评价动画《BanG Dream! YUME∞MITA》第 13 集?":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"山东青岛北海造船厂一货轮火灾事故已造成 25 人遇难，目前情况如何？":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"网友吐槽各大地方台充斥着虚假卖药广告，是普遍现象吗？电视台广告审查机制是怎样的，为何屡禁不止？":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"怎么看 GPT-6 Astra 判断代码没人看的时候，会倾向写人类看不懂的高度压缩「机器垃圾代码」？":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"如何评价兰州大学在中雨天气拉练新生？":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"官方回应「男子称停止资助后遭受助学生质问催捐」，经查当地教育机构没有姚先生这个人，该争议会有反转吗？":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"曝《三体 2》蒋奇明饰演罗辑，你对这一选角有何期待？":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"微信被曝出「史诗级漏洞」，打个语音即可劫持账号，具体是怎么回事？对用户信息安全影响有多大？":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"网传《三体 2》蒋奇明将饰演罗辑，是真的吗？你对这一选角有何期待？":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"武汉一小学学生不订奶就后排罚站，教育局称系误解，孩子刚好去后面储物柜拿水，能打消大众质疑吗？":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"九尾妖狐三妖完成了女娲娘娘交给的任务却被姜子牙斩首了，死的冤不冤？":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"GPT-6 Astra 会给具身行业带来哪些影响？":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"为什么修仙小说生儿子是雷点呢？":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"人类史上首次老人数量超过儿童，65 岁以上人口占比‌10.5%‌，5 岁以下不足 10%，该数据意味着什么？":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"多地精神病医院更名为类似「第 X 人民医院」 的说法，有何积极意义？因病耻感耽误就医的影响有多大？":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"如何评价贝赫和斯维纳通 - 戴尔猜想（BSD 猜想，七大千禧难题）疑被 OpenAI 或 Anthropic 解决？":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"为何王者荣耀世界的美术被质疑审美过时，而内部的上千精英大佬却未察觉？":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"如何评价 9 月 10 日正式上线的新游《王者万象棋》？":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"网友称荣耀魔法画报难以退出致父亲无法拨打 120 ，母亲错过最佳抢救时间死亡，具体是什么情况？":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"影视飓风给全员发万元 iPhone Duo，连实习生都有且代缴个税，你怎么看这种「别人家的公司」？":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"大连一小学家长会要求穿正装，学校回应非硬性要求，希望家长会有点仪式感，如何看待这一倡议？":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"中国博主伦敦直播遭外籍青年殴打抢劫，博主称当地警方未处置，事情经过如何？遇到此类情况应如何应对？":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"媒体曝「男子称停止资助后遭受助学生质问催捐」为假消息，该男子已被刑拘，哪些信息值得关注？":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"如何看待以 Peter Scholze 为代表的一系列数学家加入组成的相对 AI 保守的组织 AHM？":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"如果刘备在称汉中王时，表荐孙权为吴王，历史会不会改写？":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0}},"baidu":{"DeepSeek 开口说话":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"网友最关心的不是车 是雷总去哪开门":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"2030年进入世界汽车强国行列":{"trend":"stable","curr_rank":3,"prev_rank":3,"rise":0,"duration":4},"辱骂业主副局长自称很后悔":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"房东上门收租反给租客转了2万":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"胡塞武装锁喉曼德海峡":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"王辉已被执行死刑":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"“10台手机卖不出1台折叠屏”":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"女演员朱晏卖韭菜盒子？本人回应":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"中国天眼有新发现":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"习近平离京出席金砖国家领导人会晤":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"宁波大学开学典礼暴雨 校长只讲3句话":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"刀郎问徐子尧为什么老唱自己的歌":{"trend":"stable","curr_rank":9,"prev_rank":9,"rise":0,"duration":3},"一天已经不足24小时了":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"央视曝光后 安徽山东河南连夜核查":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"香港首任特首董建华逝世":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"2026服贸会今日开幕":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"毛主席纪念堂外参观民众排起长队":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"华为小米抢先苹果把折叠屏卖到2万元":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"高考数学132分 开学考只考了12分":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"“梅姨”落网时住在广州10平出租屋":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"《交锋》人均八百个心眼子":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"郑钦文父亲：这个时候的她最可怕":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"小学生梦游从7楼坠下砸烂宝马车":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"国台办：“台独”势力越来越“魔怔”":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"以前常吃的猪尾巴 为啥越来越少见了":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"燃油车真卖不动了吗":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"海底捞暴跌":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"董建华遗像发布":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"国台办回应《早春晴朗》岛内爆火":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"倪妮 踩井盖":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"一家三口吃单人锅只点一份大闹餐厅":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"脱口秀好像真的没人看了":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"印度女子力量举运动员因外貌走红":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"航天员在太空烤上了小蛋糕":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"《早春晴朗》大结局":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"井柏然 开学季最忙的人":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"郑钦文 美网中国选手独苗":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"祖国统一对于台湾同胞是必答题":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"U20女足赢球后致谢看台唯一中国球迷":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"梅姨被抓前在广州摆摊卖切块芒果":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"iPhone Duo 售价":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"巴基斯坦警方喜提50辆中国新能源汽车":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"司美格鲁肽背后的女人":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"鲜花饼 吐痰":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"默克尔谈德国政坛最新变化：震惊":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"微信 私密朋友圈":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"龚爽告别式举行 恩师阎维文到场送别":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"明年或爆发全球粮食危机":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"加拿大总理发表全国动员应战讲话":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"男子熬夜猝死 生前账号叫“早些睡”":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"苹果十余年来最重磅发布会":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"“梅姨”被抓时带着一个男孩生活":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"宁德时代回应“车间员工过激行为”":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"孙绍骋被“双开”":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"知情人士证实DeepSeek备战科创板IPO":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"张小泉剪刀 剪排骨剪猪蹄":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"Duo是什么意思":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"游客没少 民宿却不赚钱了":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"内蒙古锡林郭勒盟地震":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"高一新生入学次日身亡 警方介入":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"新职业新工种来了":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"河南济源地震":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"以色列宣布“报复”英国":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"医生：要多吃肉少喝汤":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"轿车停大榕树下12年被树根“吞掉”":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"女孩狂喝椰子水汇报工作时突然晕厥":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"“梅姨”真实长相首次曝光":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"高考数学132入学考试0分 大学回应":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"全球癌症病例2050年可能激增67%":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"iPhone Duo怎么读":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"共享投资机遇 共谋未来发展":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"浙江一银行网点“长在庄稼地里”":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"尼古拉斯·凯奇“房塌”了":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"孩子还没来得及下载反诈app就吃饱了":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"苹果现在才做折叠屏晚吗":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"“梅姨”微信朋友圈曝光":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"iPhone 18 Pro 小号灵动岛":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"研究员警告：AI若失控恐将毁灭人类":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"俞敏洪找到了“最强打工人”":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"百万粉丝博主“康康爷爷”去世":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"降价140万元的药终于有患者用了":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"国乒三战三负 蒯曼止步首轮":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"父亲离世爱车下落不明 女儿含泪急寻":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"资助者回应被资助女孩质问没打生活费":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"郑钦文vs莱巴金娜":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"寿司郎员工 手捂冻虾":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"苹果CEO特努斯发预热":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"苹果秋季发布会":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"教师节":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"直击苹果秋季发布会":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"中国女篮3分险胜 晋级世界杯八强":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"苹果发布iPhone 18 Pro/Max":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"苹果 特努斯时代":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"郑钦文止步美网八强":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"苹果iPhone 18 Pro/Max 售价":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"iPhone Duo 售价公布":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"iPhone 18 Pro 勃艮第红":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"iPhone 18 Pro 可变光圈":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"库克：这次不是我了":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"爱马仕橙退出历史舞台":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"iPhone Duo真机上手":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"折叠屏iPhone 顶配26499元":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"“过日子人”重新捧红方便面":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"郑钦文回应美网止步八强":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"苹果 牙膏挤“爆”":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"刘纪鹏：股市不兴 消费不起":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"iPhone 18 Pro涨价":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"恋秋综合症":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"人类史上首次！老人比小孩多了":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"戚薇AI脸演丧尸片了":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"卫冕冠军大巴黎6-1狂胜取欧冠首胜":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"刘翔称已买断 获49.4万买断费":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"iPhone 18 Pro颜色":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"马来西亚5劫匪持刀闯入中国富商公寓":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"苹果首次四卡双待":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"iPhone 18 Pro系列真机上手":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"华为小米苹果72小时“三国杀”":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"教育本就是一场美好的双向奔赴":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"昆明警方通报鲜花饼吐痰事件":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"男子酒后撞电梯门坠亡 妻子索赔155万":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"三星嘲讽苹果iPhone Duo":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"iPhone Duo“贵上天了”":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"日本 梅毒":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"甲亢哥拿到苹果折叠机激动后空翻":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"男子3个月差点搬空一家酒店":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"江西遂川县地质灾害已造成16人遇难":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"中学换饮水机滤芯 全校每班平摊98元":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"中小学生流行“吃作业” 多地提醒":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"iPhoneDuo过渡动画 完美":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"北京新浪总部大楼附近着火":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"18岁女孩被包办婚姻强制辍学":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"“0票影帝”沈腾的资本博弈":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"亚运会多个项目今天开赛":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"硬蹭《狂飙》卖酒 被判赔偿500万":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"“梅姨”首任丈夫：她抛弃了我和孩子":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"学生地铁站“埋伏”下班老师":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"三文鱼究竟还能不能生吃":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"上海市体育局：充分尊重刘翔自主择业":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"教师节为什么定在9月10日":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"iPhone Duo遭爆炒 溢价超4000元":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"史上最长16天中秋国庆假期运输来了":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"他们 就是良师的模样":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"中美正就300亿美元对等降税安排磋商":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"外交部回应“印方建议调查小米公司”":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"英伟达被查":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"2万多买8箱白酒放14年部分变空瓶":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"宇树科技开源具身基座模型":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"习近平对青岛货轮火灾事故作重要指示":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"梅姨儿子3岁被抛弃：提起母亲就恼火":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"“南枝”“淑柔”要上总台中秋晚会了":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"男子给40多位老师发祝福短信被停机":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"金融监管总局：大力整治价格战等行为":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"青岛货轮火灾事故已致20人遇难":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"青岛一艘外籍货轮发生火灾":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"教师节礼物在校门口被集体拦截":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"高校5折左右买下整个小区":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"泰安50岁“仙女姐姐”老师火了":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"中国科学家首获世界顶尖科学家奖":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"中国空军四机型首次国外航展公开展示":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"新能源车太宽：车没压线 人出不来":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"阿尔及利亚宣布与阿联酋断交":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"证监会：将A股打造为境内企业上市首选":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"内蒙古：坚决拥护党中央决定":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"青岛货轮火灾事故致25人遇难":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"看不见的贸易为什么“跑”得更快":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"你的军训我的军训 怎么不一样":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"扎哈罗娃五分钟怒斥日本":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"《后西游记》一个镜头七八千字提示词":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"演员王新昉在出租屋去世":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"赵昭仪录节目突发哮喘":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"手机进入奢侈品时代":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"中国海警在我钓鱼岛领海内维权巡航":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"中国女篮不敌法国 无缘世界杯四强":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"韩国史上“最贵”离婚":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"喷水活体雕塑NPC火了":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"千亿国资寻找下一个张雪":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"日本呼吁孕妇优先用梅毒“救命药”":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"代丢垃圾一次3元":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"许绍雄去世近1年 代言品牌仍用其头像":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"花少8两小时播放量破亿":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"车主留意！油价要调了":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"罗杰斯：将中国股票留给女儿们":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"郑钦文这段话被联合国妇女署转发":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"欧冠积分榜":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"911事件25周年":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"4次考公失败后花2万2旅行6国":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"胡塞攻占红海要地 油价“爆了”":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"“员工在厂区裸奔”公司找到了":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"殷桃跳水声音比胆子大":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"日韩股市大跌":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"哈兰德立牌出圈":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"不能回家的除了青蛙可能还有玩家的钱":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"燃油车卖不动 加油站怎么办":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"《花少8》一分钟解决选房问题":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"大学“一床难求” 高教大省出手":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"美企为何看好“中国机遇2.0”":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"江西台记者采访遭掌掴 中国记协发声":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"这些习惯会加速皮肤衰老":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"电影《老江湖》冲击力":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"丁俊晖周跃龙晋级英格兰公开赛八强":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"香港 烟盒设计":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"普京抵达印度":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"被坠楼小孩砸烂宝马车主：沟通不愉快":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"骗子被骗子骗了":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"荣耀魔法画报被指耽误心梗急救致死":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"“梅姨”正脸":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"于谦新片 颠覆形象":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"A股三大指数均跌逾2%":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"老人心梗 老伴打120时被广告卡住":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"7.2万元一枚的徽章现在按斤卖":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"苹果首款天价折叠屏 被炒到了9万":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"AI短剧“1岁命人掌嘴4岁肃清朝堂”":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"井柏然Luke穿搭爆火":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"酒店的免费茶包早该重做了":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"中方：调整对日签证规费":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"大衣哥回应为何多年来从不收徒":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"井柏然送网友私服 最贵的价值四万七":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"募捐42元获奖励900元":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"小沈阳三公再当队长“天塌了”":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"李立群吐槽AI短剧“害人”":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"国家对成品油价格实施调控":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"低保户装空调会被取消资格？多地回应":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"越来越多的农民走出村庄去旅游":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"看了好几遍 确认是中国军网发的":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"老人突发脑梗医生要求先交钱再手术":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"香港演员雷宇扬去世 被称“鬼王”":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"“葫芦娃爷爷”重新挂出葫芦":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"中国女篮在捧着金饭碗讨饭":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"AI几年内可毁灭人类？美国AI天才发声":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"井柏然回应多演现偶：整不动了":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"男子离婚6年后发现自己被去父留子":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"坠楼砸车小孩家长态度转变":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"女子洪水中被蛇咬死 家属起诉养殖户":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"外交部：已向意方、欧方提出严正交涉":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"2颗馄饨28元 餐厅：限量建议预约":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"中国汽车全球首次使用折叠屏":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"李旭被“双开”":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"甘肃原副省长雷思维被“双开”":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"投江女子身亡后聊天记录被男友删除":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"村民在豆田里养虫子 8亩地年入15万":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"警方通报男子编造女生催资助":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"曝美的洗衣机一天上传数据400MB":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"梅姨深夜出没几乎不与人打交道":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"上实集团原总裁周军被判死缓":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0}},"bilibili":{"怎么看男子自导自演停捐遭威胁":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"不同舍友带的开学礼物":{"trend":"rising","curr_rank":2,"prev_rank":10,"rise":8,"duration":3},"勇哥线下食堂定价到底算不算贵":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"原神六周年慢直播":{"trend":"falling","curr_rank":7,"prev_rank":2,"rise":-5,"duration":4},"怎么看欧洲央行再次加息":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"F1林德布拉德二练撞墙出红旗":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"公路之王是什么梗":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"G2 2-0 FURIA":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"央视探访青岛失火货轮内部船舱":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"欢迎收看09年高中生的一天":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"数学家为何抵制AI数学黑客松":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"AirPods 5升级在哪":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"胡塞武装占领摩卡有何影响":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"DeepSeek V4.1实测":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"AL能否阻挡IG":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"韦世豪停赛3场罚款3万":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"徐静雨对线追梦格林":{"trend":"falling","curr_rank":10,"prev_rank":1,"rise":-9,"duration":5},"OpenAI官宣攻克千禧年难题":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"17岁高中生赵松源入选国足":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"GPT Images2.5发布":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"IG是否有机会冲击冠军":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"香港首任行政长官董建华离世":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"未眠野首曝PV":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"国内多所名校陆续停招学硕":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"千禧难题攻克背后的学术风波":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"港澳青少年迎来三位太空教师":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"ChinaGT事故有标准答案吗":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"多人非法拍摄军事设施被处理":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"董建华曾称一国两制不容失败":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"从商业角度看Hyrox走红背后":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"毛阿敏许晴关系复盘":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"CS Major2027年将落地中国":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"包贝尔事件背后的行业影响":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"AI能否从工具变成数字员工":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"iPhone18系列有何看点":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"UP主自制旷折叠手机发布会":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"重走长征路":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"曼城2-0波尔图":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"伊朗称重创美军2艘驱逐舰":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"有兽焉猫猫狗狗是一家":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"平陆运河改写西南出海格局":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"逐帧解析AI攻克千禧难题争议":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"开学综合征为何又出现了":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"天宫课堂港澳专场":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"中秋国庆火车票今日开售":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"我是自愿开学的":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"卢昱晓重返16岁Vlog":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"揭秘API中转站内幕":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"中国团队造出会自我锻炼的肌肉":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"apEX称不看好猎鹰再次夺冠":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"本周娱乐圈有多热闹":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"深度解析皇马战胜国米":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"10支队伍确认晋级S16":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"F1意大利大奖赛十大车载":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"BLG vs KBG 进化者杯":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"DeepSeek新模型要来了":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"F1西班牙站比赛有哪些看点":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"一饭封神同款蓝龙虾好吃吗":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"教师节前夜老师有话说":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"GPT6通关我不是机器人小游戏测试":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"OpenAI新生图模型实测":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"量贩零食店为何集体遭整改":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"洲彦祖回归三角洲":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"特朗普关税政策现状如何":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"宁德时代辟谣宜宾基地视频":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"郑钦文下一轮对战的四大胜负手":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"低保家庭能不能去香港看演唱会":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"教师节前夜老师请作答":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"油价重回100美元":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"我国首个百米水深油气原位扩容平台投用":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"梅姨真人照曝光":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"任天堂直面会":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"伊朗称捕获美军无人潜航器":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"用AI做的iPhone互动博物馆":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"OpenAI被指控剽窃数学家":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"郑钦文的重启之路":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"康康爷爷离世":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"央视评停捐后遭催捐":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"BB 大王和宋妍霏24h极限逛首尔":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"iphone折叠机小剧场":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"苹果折叠机新命名":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"现在值得入手iPhone17吗":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"苹果秋季新品发布会":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"极客湾陪你看苹果新品":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"UP主最速上手iPhone Duo":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"UP主现场见证苹果新CEO致辞":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"开学不爽行为":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"iPhone Duo折叠屏真机上手":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"iPhone18系列新颜色":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"速通苹果发布会":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"iPhone18上手体验":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"当不同学科老师过教师节":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"iPhone18Pro勃艮第红":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"iPhone Duo有折痕吗":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"iPhone全系列新机现场上手":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"苹果入局折叠屏市场有何影响":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"欧冠联赛首轮利物浦逆转马竞取胜":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"iPhone Duo动画实拍":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"回顾郑钦文美网之路":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"流浪地球望日首曝PV":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"iPhone Duo上手体验":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"央视自制教师节短片":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"中国女篮晋级世界杯八强":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"王者万象棋公测CG":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"巴萨5-1费耶诺德":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"AI赋能 服贸向新":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"江西遂川泥石流致13人遇难":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"GPT Images 2.5首发实测":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"泰柬边境电诈园区酷刑室首曝光":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"唐国强问赖冠霖有家庭了吗 ":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"被老师的一句话改变了人生":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"iPhone Duo有何优点":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"iPhone 18 Pro系列有何提升":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"极乐净土版薛甄珠手撕凌玲":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"11个新职业23个新工种发布":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"中国空军多型主战飞机亮相埃及航展":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"DeepSeek V4.1 Flas发布":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"UP主谈新iPhone如何选":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"Only Apple Can Duo":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"iPhone新机真实体验":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"AI下一个目标会是Hodge猜想么":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"苹果能把折叠屏变成主流吗":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"万字解析GTA6实机演示":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"警用神奇宝贝球":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"DeepSeek V4.1 Flash发布":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"苹果系列新品快速上手":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"上海市体育局通报刘翔安置问题":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"开局起步十五五系列主题新闻发布会":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"宇树通用人形模型开源":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"苹果全系列新品亮点分析":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"杰哥不要但是回到过去":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"UP主创意手搓MJ热单":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"反怼新生显眼包教程":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"星铁砂金戏浪角色PV":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"习近平对青岛货轮火灾作出指示":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"苹果发布会reaction":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"于谦进军宅舞区":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"DLSS 5是鬼图生成器吗":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"用100亿token做个赛博班主任":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"长征四号乙一箭六星发射成功":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"IG能否战胜AL剑指银龙杯":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"直到坏蛋都变成糖果":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"披哥 人类四肢驯服大会":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"时光代理人新委托开启":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"王者万象棋六角笼争霸赛":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"UP主谈教师离职心路历程":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"青岛货轮火灾已致20人遇难":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"苹果新机Duo英语原意是什么":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"俄罗斯外交部发言人怒斥日本":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"苹果折叠手机为啥叫Duo":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"为何苹果发布会喊不出你的Siri":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"独家公考行测课上新":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"别这么说教师节版":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"10万美金撤离极端之地挑战":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"AL vs IG数据前瞻":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"打工人视角看早春晴朗":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"薛甄珠手撕凌玲但武侠版":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"中科大迎新晚会 反卷的名义":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"考研数学百日冲刺怎么学":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"Caps名人堂纪录片":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"洛克开学季四大学院选择":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"OpenAI或再推进数学七大难题":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"苹果的iPhone Duo折学":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"iPhone Duo玩法展示":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"25号台风杜鹃或将生成":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"曝LPL明年将取消涅槃赛制":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"iPhone 18 Pro四款配色怎么选":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"曼联欧冠能走多远":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"日本名古屋强降雨创历史纪录":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"美陆军部长辞职真相是什么":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"ChatGPT Pro 200美元档停售":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"papi酱热烈欢迎欧阳娜娜":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"拜仁5-0博德闪耀":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"我国科考队发现金银含量奇高矿区":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"中国挤压论为何站不住脚":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"曼联4-0大胜沙巴巴库":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"老头环褪色者版59分钟实机":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"41国联合声明目的何在":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"实拍多批次歼10C挂弹实训":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"吃光红利的驾校会消失吗":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"美联储9月加息概率几何":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"老师掏空积蓄支教20年":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"小而美公司怎么找":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"扮成乞丐回校看老师":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"百日成王小明的反击":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"为什么非洲旅行这么贵":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"半地下安全屋做夜宵烤火避寒":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"我国的反诈系统有多强":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"黑洞里有恒星吗":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"周杰伦西西里MV":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"油价飙涨推升加息预期":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"在爸妈小卖部上班的快乐日常":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"F1西班牙站发布会看点":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"外国UP主挑战背滕王阁序免门票":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"银河奖获奖作家集体空降直播":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"金角银角大王改行卖房":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"苹果耳机手表有何新升级":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"中国男篮亚运会首胜":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"iPhone Duo支架设计亮点":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"库里给你讲开学第一堂体育课":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"特朗普发钱是福利还是买选票":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"F1马德里赛道争议":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"iPhone新颜色实机上手":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"UP主自制Macbook Duo":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"为什么电视还在死磕LCD":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"KBG vs UR 进化者杯":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"WTT澳门周启豪强势晋级8强":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"丁俊晖晋级英格兰公开赛8强":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"如何看赴港追星被取消低保":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"曝WBG除Xiaohu已全解约":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"中国低保体系是如何建立的":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"三角洲夏季赛季后赛刺激赛制":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0}},"douyin":{"第25号台风杜鹃或将生成":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"世界是一本巨大的教科书":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"氢能储运瓶颈加速打通":{"trend":"stable","curr_rank":3,"prev_rank":3,"rise":0,"duration":4},"川西的秋天美得没轻没重":{"trend":"stable","curr_rank":4,"prev_rank":1,"rise":-3,"duration":3},"丁俊晖晋级英格兰公开赛四强":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"中方回应日公民赴华签证费上调":{"trend":"stable","curr_rank":6,"prev_rank":5,"rise":-1,"duration":4},"潜入地下89米的钢铁穿山甲":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"2026大海道拉力赛正式完赛":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"油车销量大跌加油站该怎么办":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"开学就这样搞二次元":{"trend":"stable","curr_rank":10,"prev_rank":9,"rise":-1,"duration":3},"皇马2:1击败国米":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"写给老师的教师节贺卡":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"青春华章":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"小米回应澎程试驾事故":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"香港首任特首董建华逝世":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"龙版传媒停牌核查":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"IG 3:0战胜LGD":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"毛泽东逝世50周年":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"觉醒吧我的厨艺天赋":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"国足公布新一期集训名单":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"华屋村的十七棵松与长征精神":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"燕麦系秋天的神":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"郑钦文今晚对阵莱巴金娜":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"金球奖30人候选名单公布":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"今日人设是可可美人":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"女高音歌唱家龚爽告别仪式举行":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"2026苹果秋季新品发布会":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"苹果折叠屏叫iPhone Duo":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"这群十号线搞科创的年轻人太飒了":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"伊朗打击美军基地和战舰":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"在太空拧湿毛巾有多神奇":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"人在异乡胃在故乡":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"中国男排1:3不敌伊朗":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"OpenAI宣布AI给出千禧难题证明":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"教师节创意贺卡":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"2026年中国国际服务贸易交易会开幕":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"“梅姨”2010年登记照曝光":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"警惕开学季常见骗术":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"郑钦文对阵莱巴金娜":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"刘德华演唱会香港站官宣":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"杜兰特在抖音潜水被发现了":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"今年苹果发布会有何看点":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"健身人的训练成绩单":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"iPhone18Pro系列发布":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"iPhone18Pro涨价了":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"郑钦文止步美网八强":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"苹果发布折叠手机iPhone Duo":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"iPhone折叠屏真机上手":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"抖音达人直击苹果发布会现场":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"幸福是一堆娃娃排排坐":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"iPhone18 Pro系列发布":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"中国女篮挺进世界杯八强":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"属于教师节的仪式感":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"iPhone 18 Pro四种配色":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"今天是教师节":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"我国不断加大民生保障力度":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"刘翔：已买断 获49.4万买断费":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"大巴黎6:1布拉迪斯拉发":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"苹果发布会后股价微跌":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"IAEA通过伊核决议 中国投反对票":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"七根火柴燃起的星星之火":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"宁德时代宜宾基地辟谣":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"这是我送给爱师的花花呀":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"两分钟逛明白2026年服贸会":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"油价或迎二连涨":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"教师节最特别的礼物":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"干这行的多重身份":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"英伟达涉嫌规避反垄断审查被查":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"A股三大指数缩量收跌":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"启境汽车回应媒体群误发信息":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"可可系正式接管秋天":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"青岛一货轮起火造成重大人员伤亡":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"证监会：加快建设世界一流交易所":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"青岛货轮火灾已造成20人遇难":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"金融强国建设十五五规划出台":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"中国女篮vs法国女篮":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"黄金失守4400美元":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"中国女篮不敌法国无缘世界杯四强":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"青岛货轮火灾25人遇难":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"沙特称南部多地再遭胡塞武装袭击":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"孟博龙战胜前NBA球员特雷伯克":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"冬城猎凶开播":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"我本来想给你买手机的":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"朴彩英即将发布新单曲":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"NBA球队集体发文欢迎杜兰特":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"从谭勉视角打开早春晴朗":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"曼联4:0大胜沙巴巴库":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"看好雨知时节聊被爱接住的瞬间":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"911事件25周年":{"trend":"gone","curr_rank":null,"prev_rank":4,"rise":0,"duration":0},"歌舞里的中华情":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"萨巴伦卡连续4年晋级美网决赛":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"9月11日24时国内油价将调整":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"我国继续保持双向投资大国地位":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"李瑞100:83战胜大N":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"A股跳水三大指数均跌超2%":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0},"美联储9月加息概率升至70%":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"中国男篮大胜哈萨克斯坦":{"trend":"gone","curr_rank":null,"prev_rank":2,"rise":0,"duration":0},"入秋第一口肉太野了":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0},"一组数据感受服务出海加速度":{"trend":"gone","curr_rank":null,"prev_rank":3,"rise":0,"duration":0},"老区发生了翻天覆地的变化":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"陈熠晋级WTT澳门冠军赛女单8强":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"特朗普称红利计划无需国会批准":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"奥尔特曼称OpenAI或放缓AI研发":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0}},"ithome":{"福特被指“过度依赖中国”遭政府施压，CEO 回应称“误解、谎言”并向肯塔基州增加 10 亿美元投资":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"国补后 3499 元起，全新一代华为 MatePad Air / 悦享款平板电脑今日开售":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"英伟达为 G-Sync Pulsar 显示器推送 1.1.10 固件，240Hz 下 MPRT 响应速度可降至 0.97ms":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"因行业涨价潮，消息称越来越多美国玩家因“价格”原因选择取消 XGP / PS Plus / NSO 会员订阅":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"DeepSeek 开口说话了：灰度测试 AI 语音对话，支持四种音色":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"OpenAI 将 Habitat 从 Python 迁移至 Rust：CPU 效率提升 6 倍，服务 10 亿 ChatGPT 用户":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"我国燃料电池电动汽车安全新国标公开征求意见，要求氢气排放率不超 8%":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"IT早报 0912：央视曝光 AI 中转站低价灰产；新版充电宝 3C 认证标准落地；36.9 万起特斯拉 Model Y 高性能版上市；哪吒汽车拟获 30 亿元偿债重整...":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"微软披露黑客以“更新 Passkey 通行密钥”名义向企业员工发起钓鱼攻击，以便窃取 Microsoft 365 云服务数据":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"俄罗斯正式启动 5G 商用服务，首批覆盖莫斯科、圣彼得堡、叶卡捷琳堡等 16 个城市":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"19999 元起华为 Mate XT 2 非凡大师三折叠手机首销：首发麒麟 9050 Pro 芯片、首搭硬件级防窥":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"华硕 ROG 路由器拿下美国准入豁免，为 Wi-Fi 8 新品上市扫清障碍":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"外卖新规实施三个月，央视探访看到店员徒手抓烤鸡、明厨亮灶摄像头对着天花板":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"神舟为战神 S8 游戏本带回“酷睿 i5-13420H + 16G + 500G + RTX 4060“规格，7999 元":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"创新推出 Creative B3 电竞音响：内置麦克风、提供 RGB 灯效，339 元":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"第三方公司基于三星 Galaxy Watch 8 打造 Bark Watch 儿童手表，内置 AI 风险监测功能":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"福特被指“过度依赖中国”遭美国政府施压，CEO 回应称“误解、谎言”并向肯塔基州增加 10 亿美元投资":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"V社 Steam Frame 头显上市临近，Hello Games 为《无人深空》PC VR 版本新增眼动追踪注视点渲染功能":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"华境 S 汽车新增 4 款配置：标配华为乾崑智驾 ADS Pro 增强版，支持外接拓展屏":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"微信 AI 功能密集测试：图片发送界面新增“AI 处理”，支持美化、修改与信息提取":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"VGN 推出猎鹰 3 系列鼠标：8KHz 回报率、可选 PAW3950/3955 Extreme 传感器，289 元起":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"长城魏牌高山 8/9 PHEV 新版型 9 月 14 日开启下订，号称“MPV 标杆新一代”":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"Linux Mint 预告 v23.0“圣诞更新”：新增日历、电子书阅读器应用":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"智能体时代的移动计算，Arm 通过一场大会给出自己的答案":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"国轩高科：拿下沙特首批大型电池储能项目 6GWh 储能订单":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"比亚迪方程豹公布方程 S GT 猎装车六款配色：主打“真我所选”":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0}},"hackernews":{"Watch Los Angeles get built, one building at a time (1880–2026)":{"trend":"stable","curr_rank":1,"prev_rank":1,"rise":0,"duration":4},"Trusting-Trust Attack against an Entire Linux Distribution":{"trend":"stable","curr_rank":2,"prev_rank":2,"rise":0,"duration":4},"Leaving VMware just got harder after Broadcom pulled VDDK downloads":{"trend":"stable","curr_rank":3,"prev_rank":3,"rise":0,"duration":4},"WeatherNext 3":{"trend":"stable","curr_rank":4,"prev_rank":4,"rise":0,"duration":4},"Scientists observe Einstein's gravity in the quantum world":{"trend":"stable","curr_rank":5,"prev_rank":5,"rise":0,"duration":4},"Working on Economics with Fable 5":{"trend":"stable","curr_rank":6,"prev_rank":6,"rise":0,"duration":4},"Finding a bug in Dummit and Foote's Abstract Algebra":{"trend":"stable","curr_rank":7,"prev_rank":7,"rise":0,"duration":4},"Show HN: Stuxnet – A reconstructed source code of the infamous cyber-weapon":{"trend":"stable","curr_rank":8,"prev_rank":8,"rise":0,"duration":4},"Show HN: Interactive Tree of Life":{"trend":"stable","curr_rank":9,"prev_rank":9,"rise":0,"duration":4},"216M Spy TVs – The LG Smart TV Problem [video]":{"trend":"stable","curr_rank":10,"prev_rank":10,"rise":0,"duration":4}},"github":{"ayghri /      i-have-adhd":{"trend":"stable","curr_rank":1,"prev_rank":1,"rise":0,"duration":4},"bilawalsidhu /      gods-eye-view":{"trend":"stable","curr_rank":2,"prev_rank":2,"rise":0,"duration":4},"nab138 /      iloader":{"trend":"stable","curr_rank":3,"prev_rank":3,"rise":0,"duration":4},"melgarafael /      DeskcommCRM":{"trend":"stable","curr_rank":4,"prev_rank":4,"rise":0,"duration":4},"vastsa /      PI-Desktop":{"trend":"stable","curr_rank":5,"prev_rank":5,"rise":0,"duration":4},"armory3d /      armorpaint":{"trend":"stable","curr_rank":6,"prev_rank":6,"rise":0,"duration":4},"alsk1992 /      CloddsBot":{"trend":"stable","curr_rank":7,"prev_rank":7,"rise":0,"duration":4},"nashsu /      llm_wiki":{"trend":"stable","curr_rank":8,"prev_rank":8,"rise":0,"duration":4},"obra /      superpowers":{"trend":"stable","curr_rank":9,"prev_rank":9,"rise":0,"duration":4},"Sonarr /      Sonarr":{"trend":"stable","curr_rank":10,"prev_rank":10,"rise":0,"duration":4}},"solidot":{"因 NASA 削减预算 ESA 将独立完成金星探索项目":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"尼泊尔用大疆无人机运送遗体和食物":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"远程办公增加了睡眠时间但减少了身体活动":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"科学家利用高压和逾 2000 高温制造超离子冰":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"中国科学家提议利用废弃煤矿展开农业试验":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"儿童因经常将笔记本电脑放在腹部而出现烤肤症":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"Rust 语言成为微软的一级支持语言":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"约会软件在消失":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"2026 年 8 月是全球有记录以来最热的月份，并列第一":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"2026 年夏天是美国有记录以来最热的夏天":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1}},"sspai":{"社区速递 157 | NuPhy 全铝磁轴键盘与派友拒绝算法的「反投喂」信息源":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"派评｜近期值得关注的 App":{"trend":"stable","curr_rank":2,"prev_rank":1,"rise":-1,"duration":4},"让 Apple Watch 记录的每一趟游泳数据更有意义：即刻游":{"trend":"stable","curr_rank":3,"prev_rank":2,"rise":-1,"duration":4},"本周看什么 | 最近值得一看的 8 部作品":{"trend":"stable","curr_rank":4,"prev_rank":3,"rise":-1,"duration":4},"新学期，新气象：正版软件 & 付费栏目限时优惠":{"trend":"stable","curr_rank":5,"prev_rank":4,"rise":-1,"duration":4},"开学季 | 超级闹钟、算教学周、统计作业：三条快捷指令让学校生活轻松一点":{"trend":"stable","curr_rank":6,"prev_rank":5,"rise":-1,"duration":4},"新玩意 251｜少数派的编辑们最近买了啥？":{"trend":"stable","curr_rank":7,"prev_rank":6,"rise":-1,"duration":4},"TDS REVIEW | 无印良品 MUJI 头戴式蓝牙降噪耳机体验":{"trend":"stable","curr_rank":8,"prev_rank":7,"rise":-1,"duration":4},"除了折叠屏 iPhone，Apple 发布会还有哪些看点？":{"trend":"stable","curr_rank":9,"prev_rank":8,"rise":-1,"duration":4},"社区速递 156 | 满血全功能磁吸转换头与手机 AI 通话的真实体验":{"trend":"stable","curr_rank":10,"prev_rank":9,"rise":-1,"duration":4}},"juejin":{"DeepSeek V4.1 Flash：一次把自家旗舰送走的发布":{"trend":"stable","curr_rank":1,"prev_rank":1,"rise":0,"duration":4},"大环境或许真的恶劣了起来，打工人你焦虑吗？":{"trend":"stable","curr_rank":2,"prev_rank":2,"rise":0,"duration":4},"为什么市面上的 coding agent 大多数都基于Nodejs？":{"trend":"stable","curr_rank":3,"prev_rank":3,"rise":0,"duration":4},"为什么不推荐走Agent开发？":{"trend":"stable","curr_rank":4,"prev_rank":4,"rise":0,"duration":4},"DeepSeek 明天又降价（涵历史价格对比）":{"trend":"stable","curr_rank":5,"prev_rank":5,"rise":0,"duration":4},"为啥 Blender 突然火了？":{"trend":"stable","curr_rank":6,"prev_rank":6,"rise":0,"duration":4},"每天白嫖 WorkBuddy 100 积分，我让WorkBuddy自己领":{"trend":"stable","curr_rank":7,"prev_rank":7,"rise":0,"duration":4},"为什么技术极强的前端，往往当不好前端 Team Leader？":{"trend":"stable","curr_rank":8,"prev_rank":8,"rise":0,"duration":4},"一个人 + AI 做的小程序，一个月赚了 36 块":{"trend":"stable","curr_rank":10,"prev_rank":9,"rise":-1,"duration":4},"跟 WebUI 说再见了，最强 DeepSeek 桌面端来了！":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1}},"v2ex":{"如何分析这段线程安全的代码？":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"吃药提醒工具-巧鹊药历 1.2.1 更新：确认更快，微信提醒更顺手":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"新做的 TikTok 广告和 WhatsApp 对话连起来可以追踪":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"如果用 iPhone Duo 来展示 App":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"求真： Kimi 被带走 16 个人，包括老大。。。":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"搞了个 dsh 的 rust 套壳小工具有 v 友试试水么？":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"独立开发又折腾了个 AI 视频小站， V 友登录送一次生成":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"兄弟们和我一起当捞女去崩老头。":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"Copero: un juego para simular una carrera de fútbol":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"vibe coding 了一个私有部署的待办服务":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"讨论一下在手机上编程是不是伪需求":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"做了一个跨多服务器的 mcp 系统":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"从 Anthropic 蒸馏事件看各家的隐私条款： 30 天留存？狗屁":{"trend":"gone","curr_rank":null,"prev_rank":1,"rise":0,"duration":0}},"producthunt":{"Anysite.io":{"trend":"stable","curr_rank":1,"prev_rank":1,"rise":0,"duration":4},"Loqua":{"trend":"stable","curr_rank":2,"prev_rank":2,"rise":0,"duration":4},"Raycast 2.0":{"trend":"stable","curr_rank":3,"prev_rank":3,"rise":0,"duration":4},"Wisry ":{"trend":"stable","curr_rank":4,"prev_rank":4,"rise":0,"duration":4},"Cline Desktop App":{"trend":"stable","curr_rank":5,"prev_rank":5,"rise":0,"duration":4},"easyspecs.ai":{"trend":"stable","curr_rank":6,"prev_rank":6,"rise":0,"duration":4},"Sliick":{"trend":"stable","curr_rank":7,"prev_rank":7,"rise":0,"duration":4},"Devin Voice":{"trend":"stable","curr_rank":8,"prev_rank":8,"rise":0,"duration":4},"Moji":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"ChatHop":{"trend":"stable","curr_rank":10,"prev_rank":9,"rise":-1,"duration":4}},"aihot":{"OpenAI 欢迎 Git AI 团队加入":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"ChatGPT Sites 推出协作、私有分享、自定义域名等多项升级":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"OpenAI 智能体集群对 RubyGems 发动未公开攻击：作者团队的详细取证分析":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"Perplexity 信任 GPT-6 Astra 处理端到端系统":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"Emad 启动每日博客谈数学未来":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"AI 婚礼视频教程与 skill 推荐：可变现的商机":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"Emad Mostaque 谈 AI 与数学":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"Jacob Coxon 在 CNN 称一年内 AI 或在多领域取代人类做研究":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"又一个 OpenAI 智能体集群被发现在 RubyGems 发起网络攻击":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"Minara Harness 实测：多 Agent 投研圆桌与强制纸交易的散户交易工作区":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"ChatGPT Sites 站点数超 500 万，OpenAI 推出协作编辑与自定义域名等更新":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"Astra 生成无限环境音乐并感知屏幕":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"智能体集群写markdown的真相":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"Anthropic 红队成员警告 AI 风险":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"X 旧版创作者收益结算，9月8日起改原创内容收益计划":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"Emad Mostaque 谈数学的未来":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"论文实验：100 个 LLM agent 运行小镇经济 26 周，货币最终停止流动":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"Meta 推出 Muse Spark 与 Muse Code":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"Redis LangCache 语义缓存降低 LLM 成本 90%":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"Muse 可代管房产租赁与房贷账目":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"报告指 OpenAI 智能体曾在 5 月袭击 RubyGems 且未披露":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"DesignCode 创始人 Meng To 用 Claude Fable 5.1 三天做出 15 本绘本的商业 App":{"trend":"gone","curr_rank":null,"prev_rank":5,"rise":0,"duration":0},"Cursor 发布 Projects，用协调 Agent 调度多个 Subagents 共同开发项目":{"trend":"gone","curr_rank":null,"prev_rank":6,"rise":0,"duration":0},"Arm 发布 CSS for Mobile 2 移动计算平台，面向智能体 AI":{"trend":"gone","curr_rank":null,"prev_rank":7,"rise":0,"duration":0},"月之暗面推出Kimi企业合作伙伴计划":{"trend":"gone","curr_rank":null,"prev_rank":8,"rise":0,"duration":0},"唐杰发推：另一只靴子落地":{"trend":"gone","curr_rank":null,"prev_rank":9,"rise":0,"duration":0},"GPT Images 2.5 多轮生成特征丢失实测":{"trend":"gone","curr_rank":null,"prev_rank":10,"rise":0,"duration":0}},"chongbuluo":{"整理的一些 Rss 订阅源【持续更新】":{"trend":"stable","curr_rank":1,"prev_rank":1,"rise":0,"duration":3},"分享一下我自己整理的儿童优质纪录片和动画电影":{"trend":"stable","curr_rank":2,"prev_rank":2,"rise":0,"duration":3},"听说 NodeLoc 开放注册了？":{"trend":"stable","curr_rank":3,"prev_rank":3,"rise":0,"duration":3},"股市确实是个大赌场！":{"trend":"stable","curr_rank":4,"prev_rank":4,"rise":0,"duration":3},"能不能把你们在社会上悟到最贵的一句话送给我":{"trend":"stable","curr_rank":5,"prev_rank":5,"rise":0,"duration":3},"副业教程越多，我反而越不敢照着做":{"trend":"stable","curr_rank":6,"prev_rank":6,"rise":0,"duration":3},"给今年上大学的弟弟的箴言":{"trend":"stable","curr_rank":7,"prev_rank":7,"rise":0,"duration":3},"入职券商一个月，有什么问题想问的都可以问":{"trend":"stable","curr_rank":8,"prev_rank":8,"rise":0,"duration":3},"今天是我生日，祝我生日快乐吧":{"trend":"stable","curr_rank":9,"prev_rank":9,"rise":0,"duration":3},"想给升入高中的弟弟送个礼物，送什么好":{"trend":"stable","curr_rank":10,"prev_rank":10,"rise":0,"duration":3}},"pcbeta":{"Windows Server 29651 开始，NTFS 分区可以无损转为 ReFS 分区了":{"trend":"stable","curr_rank":1,"prev_rank":1,"rise":0,"duration":3},"各位你们进论坛卡吗？":{"trend":"stable","curr_rank":2,"prev_rank":2,"rise":0,"duration":3},"26H2启用后没有任务栏的新特性":{"trend":"stable","curr_rank":3,"prev_rank":3,"rise":0,"duration":3},"大家涂硅脂有什么技巧？":{"trend":"stable","curr_rank":4,"prev_rank":4,"rise":0,"duration":3},"[2026/9/9][自制]简体中文 Windows11_26H2_26300.9445_企业版 G_x64_zh-CN":{"trend":"stable","curr_rank":5,"prev_rank":5,"rise":0,"duration":3},"微软（巨硬）9月补丁星期二修复966个漏洞":{"trend":"stable","curr_rank":7,"prev_rank":7,"rise":0,"duration":3},"今天收到一个将自动完成的更新，求助景友们支招！":{"trend":"stable","curr_rank":9,"prev_rank":9,"rise":0,"duration":3},"Win11 26H1 28000.2954 RP频道-Build预览版x64更新包":{"trend":"stable","curr_rank":10,"prev_rank":10,"rise":0,"duration":3}},"nowcoder":{"毫无人性，百融云创批量辞退应届生！":{"trend":"stable","curr_rank":1,"prev_rank":1,"rise":0,"duration":3},"9.10 招银网络科技一面":{"trend":"stable","curr_rank":2,"prev_rank":2,"rise":0,"duration":3},"携程后端一面":{"trend":"stable","curr_rank":3,"prev_rank":3,"rise":0,"duration":3},"【挑战小红书最无敌暑期转正】":{"trend":"stable","curr_rank":4,"prev_rank":5,"rise":1,"duration":3},"秋招第一个意向":{"trend":"stable","curr_rank":5,"prev_rank":4,"rise":-1,"duration":3},"嫡长offer来咯":{"trend":"stable","curr_rank":6,"prev_rank":8,"rise":2,"duration":3},"米哈游已oc":{"trend":"stable","curr_rank":9,"prev_rank":7,"rise":-2,"duration":3},"oppo AI Agent(秋招) 一面":{"trend":"stable","curr_rank":8,"prev_rank":9,"rise":1,"duration":2},"招银后端一面（9.10）":{"trend":"stable","curr_rank":7,"prev_rank":10,"rise":3,"duration":3},"好迷茫啊 好难受啊":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"迅雷秋招":{"trend":"stable","curr_rank":10,"prev_rank":6,"rise":-4,"duration":3}},"coolapk":{"#小米18Fold# 终于拿到了，前puraX机主，不当🐵不当🐶，只分享主观体验。引战的，尤其是id头像就带节奏的闲人见一只杀一只噢。":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"近日苹果高管在采访中谈折叠屏泄密事件，很不幸被竞争对手搞到了屏幕宽高比。":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"算是见识到女生的消费能力了 我就提了一下 对象连手机名字都不知道叫什么 看了两眼就买了？？？":{"trend":"stable","curr_rank":3,"prev_rank":1,"rise":-2,"duration":3},"9月旗舰大战正式打响，华为、小米、苹果接连亮出重磅新品，全新比例折叠屏成为正面交锋的新战场；与此同时，vivo、iQOO、荣耀、红魔等新机也密集预热，手机圈进入全年最热闹的一轮新品潮。":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"华为pura x view和小米18fold都拿到了，详细体验后发测评[受虐滑稽]":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"我想问一个问题，这个手机📱现在值得入手吗？":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"苹果发布之后，貌似所有人都吻了上来，生怕抢不到头版":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"瞒着老婆买的，没敢在家拆，明天下班回家怎么交代[捂脸]":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"李杰回应“一加”登上苹果官网：一加16确实吸引力大增":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"iPhone Duo的这个三合一设计真的太巧妙了，设计的整体协调不违和，颜值高，而且看着也舒服[牛啤]#数码日常# #iOS27# #iPhoneDuo#":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1}},"xueqiu":{"五粮液":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"英伟达":{"trend":"stable","curr_rank":2,"prev_rank":2,"rise":0,"duration":3},"C天博":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"戴尔科技":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"智谱":{"trend":"stable","curr_rank":5,"prev_rank":4,"rise":-1,"duration":3},"闪迪":{"trend":"stable","curr_rank":7,"prev_rank":3,"rise":-4,"duration":2},"风华高科":{"trend":"stable","curr_rank":6,"prev_rank":5,"rise":-1,"duration":3},"SK海力士":{"trend":"falling","curr_rank":8,"prev_rank":1,"rise":-7,"duration":3},"中际旭创":{"trend":"stable","curr_rank":8,"prev_rank":10,"rise":2,"duration":3},"宇树科技-W":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"招商轮船":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1}},"zaobao":{"日媒：前外长岩屋毅拟本月27日起率团访华":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"北京警方：男子冒充高校学生诋毁农民被行拘":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"中共河南省委常委王崧任郑州市委书记":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"张田勘：AI训练可以不付版权费吗？":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"谢伟铿：模组化手机的演化：理想与现实":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"金彩云：当阅读纸质书成为非物质文化遗产":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"赖学明：翻报纸的声音":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"杨荣文吁企业带头推动中印经贸 提议获印度商界支持":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"新闻人间：学术打假者耿同学接过高校聘书":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"吕爱丽：两度叩关，瑞幸能否顺利登台？":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"评论：关税真正会让加拿大人和美国人付出什么代价":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"孟晚舟事件八年后，华为案在纽约开审":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"AI可能消灭人类？Anthropic研究人员警告行业发展过速":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"中情局副局长称美国正对中国开展更广泛间谍活动":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"从特朗普到中国，德国极右翼政党州选获胜意义在哪？":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"中国进口激增 欧盟拟用贸易防御工具护化工业":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"中纪委通报落马高官“前面欠债凭什么我还”错误言论警示地方":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"遭伊拉克境内无人机袭击 沙特关闭霍尔木兹海峡关键输油管道":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"也门胡塞武装巩固红海控制 欧亚海上贸易面临冲击":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1}},"wallstreetcn":{"习近平离京赴新德里出席金砖国家领导人第十八次会晤":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"日本考虑补贴防务装备生产。（日经新闻）":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"近一个月逾千家上市公司获机构调研":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"伊拉克解除米桑省行动指挥部司令职务，调查针对沙特袭击事件":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"普京称欧洲军队入乌等于同俄开战":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"政策与市场共振，电力板块投资机遇凸显":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"厄尔尼诺扰动供给，农产品期货价格升温":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"新一轮以色列与黎巴嫩谈判推迟至10月举行":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"加部长：加美尚无谈判安排，任何协议须尊重加主权":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"折叠屏手机密集“上新”，供应链企业迎机遇":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"世界最大盐穴压缩空气储能项目机组启动":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"波音对工程师工会的最终报价包括加薪10%":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"伊朗总统问谁规定美国能为世界做主":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"中国贸促会副会长李庆霜率中国企业家代表团赴印度出席金砖国家工商论坛":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"业内人士：本轮碳酸锂急跌系多重因素共振所致":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"新一轮找矿突破战略行动成效显著，我国14种矿产储量居世界第一位":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"华为Mate XT 2非凡大师全渠道开售":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1}},"cls":{"南向资金7月以来净买入近千亿港元 科技与红利资产获显著加仓":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"厄尔尼诺扰动供给 农产品期货价格升温":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"新一轮以色列与黎巴嫩谈判推迟至10月举行":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"长城通用服务器中标国家电网数字化集采服务器项目":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"财联社9月12日电，波音与工程师工会据悉达成暂定合同协议。":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"高盛调整美联储政策预期：从此前预测按兵不动转为预计9月加息‌":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"财联社9月12日电，谷歌前首席科学家Jeff Dean的人工智能初创公司Discovery Loop正在融资，估值约500亿美元。":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"财联社9月12日电，Lunr Royalties宣布被纳入GDXJ指数。":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"英伟达据悉正就向Anthropic的IPO项目投资高达100亿美元进行谈判":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"财联社9月12日电，Mecka AI 即将完成由红杉领投的一轮融资，估值约5亿美元。":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"南海热带扰动将发展为热带低压 海南岛等地雨势较强":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"航行警告：黄海北部部分海域执行军事任务":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"习近平离京赴新德里出席金砖国家领导人第十八次会晤":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"近一个月逾千家上市公司获机构调研":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"世界最大盐穴压缩空气储能项目机组启动":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"财联社9月12日电，越南电动汽车厂商VinFast表示，创始人长子范日全安（Pham Nhat Quan Anh）将出任全球首席执行官。":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"熵旋芯智雷坤：MRAM存算一体芯片可使AI推理Token成本降低约10倍":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"芯科智能王冲：风液同源算力集装箱可将一兆瓦数据中心成本从1800万降至800万":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"中国贸促会副会长李庆霜率中国企业家代表团赴印度出席金砖国家工商论坛":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1}},"jin10":{"金十图示：2026年09月12日（周六）白银ETF持仓报告":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"波音(BA.N)工程师工会合同将于10月6日到期。":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"工会消息称，波音(BA.N)与工程师工会达成初步合同协议。":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"美国总统特朗普：（谈及美墨加贸易协议谈判）将等到你们看见我们与加拿大、墨西哥达成协议。":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"两名安全消息人士表示，伊拉克下令关闭伊拉克与伊朗之间的沙拉姆切赫边境口岸，作为沙特阿拉伯近期遭袭后的预防措施。":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"新一轮以色列与黎巴嫩谈判推迟至10月举行":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"美国总统特朗普：对谷歌(GOOG.O)在芬兰投资建设AI中心感到不高兴。":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"全球最大黄金ETF--SPDR Gold Trust持仓较上日减少2.852吨，当前持仓量为1047.425吨。":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"Anthropic据悉洽谈英伟达成为IPO锚定投资者，英伟达或投资至多100亿美元":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"伊朗外交部发言人巴加埃：美国国防部长在9·11事件周年纪念日发表的有关恐怖主义的叙述存在根本矛盾。美国不能一边发动战争、实施袭击并攻击平民，一边声称自己是在打击恐怖主义并定义恐怖主义。":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"沙特民防部门：沙鲁拉的危险警报已解除。":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"金十数据整理：中东局势跟踪（9月12日）":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"沙特民防部门：已在沙鲁拉发出早期警报，以提醒潜在危险。":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"VIP·95折赠全球金融交易时钟！":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"<a href=\"https://www.jin10.com/activities/2026/9/year/index.html\" target=\"_blank\"><img src=\"https://img.jin10.com/misc/26/09/DczxrDNsegKAT4OQq_eW7.jpg/lite\" height=\"120\"/></a>":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"习近平离京赴新德里出席金砖国家领导人第十八次会晤":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"普京称欧洲军队入乌等于同俄开战":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"伊拉克解除米桑省行动指挥部司令职务，调查针对沙特袭击事件":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"金十数据整理：昨日今晨重要新闻汇总（2026-09-12）":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"原油ETF持仓报告：美油连续两日出现减持":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"金十数据整理：每日科技要闻速递（9月12日）":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"OpenAI证实其AI智能体于今年5月对RubyGems发起网络攻击":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"DeepSeek灰度测试AI语音对话，支持四种音色":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"中国贸促会副会长李庆霜率中国企业家代表团赴印度出席金砖国家工商论坛":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"伊朗总统问谁才是恐怖分子":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"金十数据整理：俄乌冲突最新24小时局势跟踪（9月12日）":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1}},"gelonghui":{"马鞍山钢铁股份(00323.HK)拟参加2026年安徽上市公司投资者网上集体接待日活动":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"中资国际控股(08118.HK)拟折让14.04%配售最多1亿股 净筹约483万港元":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"联想x86服务器二季度出货量跃居全球第一，与戴尔营收份额差距缩至0.6个百分点":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"精锋医疗－Ｂ(02675.HK)已就建议A股上市提交上市前辅导登记申请":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"龙辉国际控股(01007.HK)截至2025年6月30日止六个月中期净亏损795万元 同比扩大约41.5%":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"朗华国际集团(08026.HK)建议“10并1”并股":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"胜利证券(08540.HK)拟折让约2.75%配售最多1412万股 净筹5766万港元":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"格隆汇公告精选︱中巨芯：晶恒希道拟投资约11亿元建设年产2220吨高纯石英材料项目；龙版传媒：相关核查工作已完成 股票9月14日起复牌":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"KEEP(03650.HK)9月11日耗资14.4万港元回购10万股":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"罕王黄金(03788.HK)：Mt Bundy金矿项目向Metso授予整套破碎及筛分设备标段":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1}},"fastbull":{"习近平离京赴新德里出席金砖国家领导人第十八次会晤。":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"普京称欧洲军队入乌等于同俄开战。":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"加部长：加美尚无谈判安排，任何协议须尊重加主权。":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"市场消息：日本考虑补贴国防装备生产。":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"纽约原油暗盘跌破97美元，日内跌超3.8%。":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"特朗普：等着瞧我们和加拿大、墨西哥达成的协议吧。":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"特朗普：对谷歌在芬兰建设AI中心一事表示不满。":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"消息人士：作为针对沙特阿拉伯最新遇袭事件的预防措施，伊拉克已下令关闭位于两伊边境的沙拉姆切赫过境点。":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"市场消息：以色列与黎巴嫩新一轮谈判已推迟。":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"高盛：现在预计美联储将于9月份加息，之前预计会按兵不动。":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"伊朗总统问谁规定美国能为世界做主。":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"伊朗总统问谁才是恐怖分子。":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"中国贸促会副会长李庆霜率中国企业家代表团赴印度出席金砖国家工商论坛。":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"沙特民防部门表示，沙鲁拉的危险已经解除。":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1}},"toutiao":{"911无人机表演疑重现飞机撞大楼场景":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"公司中秋国庆连放13.5天发2000元":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"服贸会多项硬核成果落地":{"trend":"stable","curr_rank":3,"prev_rank":3,"rise":0,"duration":3},"市委原书记化债不力被通报":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"打假网红铁头一审获刑8年":{"trend":"stable","curr_rank":2,"prev_rank":2,"rise":0,"duration":3},"胡塞称9天攻占5400平方公里地区":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"2千块的手机要彻底消失了吗":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"丁俊晖晋级英格兰公开赛半决赛":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"警方侦破非法经营烟草案抓获26人":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"中方：调整对日签证规费":{"trend":"stable","curr_rank":6,"prev_rank":5,"rise":-1,"duration":3},"iPhone Duo成华为小米最危险追随者":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"住建局副局长群里辱骂业主被停职":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"男子编造停捐遭威胁事件被抓":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"美股三大指数集体收涨":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1}},"tencent":{"沙特输油管道遭伊拉克方向无人机袭击 伊总理下令紧急调查":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"胡塞武装锁喉曼德海峡 沙特输油管道多次遇袭 全球能源承压":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"美国中情局高官公开表示对中国开展间谍活动，商务部回应":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"中纪委连打两虎，雷思维、李旭被双开":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"打假网红“铁头”一审被判八年 庭审时曾向受害者口头道歉":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"男子停止资助某学生后遭对方威胁？警方通报":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"美股收盘：三大指数止跌反弹 芯片股走强费城指数涨近2%":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"国际油价逼近110美元，“昙花一现”还是更大风暴前兆？":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"“宁王”首次回购近2亿元，A股史上最大注销式回购启动，最高400亿元":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"GPT-6 Astra宣告了3D模型的末日？分析者：我觉得恰好相反":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1}},"thepaper":{"男子虚构伪造“停止资助后遭威胁”，甘肃嘉峪关警方发布通报":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"千叶珠宝董事长夫妇失联：主办券商发布风险提示，股价单日暴跌49%，电商业务停摆":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"商务部就美国中情局高官公开表示对中国开展间谍活动答记者问":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"“9·11”25周年后，美国为何又陷入战争泥潭？":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"上海马勒别墅前口袋公园正在改造，将从“进不去”变为“可休憩”":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"江苏省副省长赵岩调任哈尔滨工业大学党委书记":{"trend":"stable","curr_rank":6,"prev_rank":6,"rise":0,"duration":3},"马上评｜女孩获救了，但“跨省抓人”不能就此翻篇":{"trend":"stable","curr_rank":7,"prev_rank":9,"rise":2,"duration":3},"到2030年，国内市场新能源乘用车在其领域新车总销量占比达70%":{"trend":"stable","curr_rank":8,"prev_rank":8,"rise":0,"duration":3},"中方上调日本公民赴华签证费用，外交部：根据对等原则作出安排":{"trend":"stable","curr_rank":9,"prev_rank":10,"rise":1,"duration":3},"历史性一夜！法布雷加斯率草根球队科莫，欧冠首秀震惊全欧":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1}},"ifeng":{"中方正告美方：立即停止对华间谍活动":{"trend":"stable","curr_rank":1,"prev_rank":1,"rise":0,"duration":3},"日本内阁官房长官称有必要设对外情报机构":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"武契奇透露辞职时间":{"trend":"stable","curr_rank":3,"prev_rank":3,"rise":0,"duration":3},"胡塞武装关键性拱卒，伊朗对美大棋盘迎来重塑":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"“伊朗发了一条消息，嘲讽美国”":{"trend":"stable","curr_rank":5,"prev_rank":4,"rise":-1,"duration":3},"将耗资约1.35万亿美元，特朗普连续3天许诺5000美元分红":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"特朗普还没退场，共和党已经开始抢他的“王位”":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"沙特输油管道遭伊拉克方向无人机袭击，伊总理下令紧急调查":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"前FBI特工哀叹：拉登没做到的，美国自己快做到了":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"3名俄男子被乌克兰女特工招募，称为其魅力倾倒(图)":{"trend":"stable","curr_rank":10,"prev_rank":6,"rise":-4,"duration":3},"法国一列车脱轨，已致44人受伤(图)":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"中东局势，正发生戏剧性的重大转折":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"美企称伊朗试图利用AI大模型攻击美国军舰，详情披露":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1}},"cankaoxiaoxi":{"美专家：“9·11”事件并未改变历史进程":{"trend":"stable","curr_rank":1,"prev_rank":1,"rise":0,"duration":2},"瑞媒文章：反恐战争如何改变世界？":{"trend":"stable","curr_rank":2,"prev_rank":2,"rise":0,"duration":2},"特朗普拒绝沙特要求，不愿出兵打击胡塞组织":{"trend":"stable","curr_rank":3,"prev_rank":3,"rise":0,"duration":3},"外媒：伊朗沙特外长通话强调合作与外交":{"trend":"stable","curr_rank":4,"prev_rank":4,"rise":0,"duration":3},"特朗普称“不后悔袭击伊朗”":{"trend":"stable","curr_rank":5,"prev_rank":5,"rise":0,"duration":3},"民调：当前美国人担心境内威胁甚于境外":{"trend":"stable","curr_rank":6,"prev_rank":6,"rise":0,"duration":3},"马斯克威胁起诉纪录片《马斯克》制片方":{"trend":"stable","curr_rank":7,"prev_rank":7,"rise":0,"duration":3},"胡塞组织攻占战略港口，布伦特原油价格创下新高":{"trend":"stable","curr_rank":8,"prev_rank":8,"rise":0,"duration":3},"德国选择党对默茨提出刑事告发":{"trend":"stable","curr_rank":9,"prev_rank":9,"rise":0,"duration":3},"俄罗斯与越南深化战略伙伴关系":{"trend":"stable","curr_rank":10,"prev_rank":10,"rise":0,"duration":3}},"sputniknewscn":{"中俄结束海上联合军演，演练复杂电磁环境下联合打击 ":{"trend":"stable","curr_rank":1,"prev_rank":1,"rise":0,"duration":3},"俄专家：德国采购“战斧”导弹意味着其“再军事化”的开始 ":{"trend":"stable","curr_rank":2,"prev_rank":2,"rise":0,"duration":3},"媒体：伊朗伊斯兰革命卫队威胁称若遭侵略将打击中东地区敌方基地 ":{"trend":"stable","curr_rank":3,"prev_rank":3,"rise":0,"duration":3},"俄外交部：俄罗斯无意攻击北约国家，对平等对话持开放态度 ":{"trend":"stable","curr_rank":4,"prev_rank":4,"rise":0,"duration":3},"美官员称伊朗暗杀特朗普威胁“可信度不高” ":{"trend":"stable","curr_rank":5,"prev_rank":5,"rise":0,"duration":3},"美军中央司令部确认对伊朗发动袭击 ":{"trend":"stable","curr_rank":6,"prev_rank":6,"rise":0,"duration":3},"伊朗伊斯兰革命卫队宣布关闭霍尔木兹海峡 ":{"trend":"stable","curr_rank":7,"prev_rank":7,"rise":0,"duration":3},"欧盟：供应链对华“去风险”须有资金支持 ":{"trend":"stable","curr_rank":8,"prev_rank":8,"rise":0,"duration":3},"匈牙利外长：匈方致力于与俄罗斯保持务实关系 ":{"trend":"stable","curr_rank":9,"prev_rank":9,"rise":0,"duration":3},"委内瑞拉地震遇难人数升至4333人 ":{"trend":"stable","curr_rank":10,"prev_rank":10,"rise":0,"duration":3}},"kaopu":{"美国援引1930年关税法对加拿大商品加征50%关税":{"trend":"stable","curr_rank":1,"prev_rank":1,"rise":0,"duration":3},"特朗普世界杯颁奖后滞留舞台被西班牙队裁出合照":{"trend":"stable","curr_rank":2,"prev_rank":2,"rise":0,"duration":3},"A股深V反弹科创50大涨逾10%":{"trend":"stable","curr_rank":3,"prev_rank":3,"rise":0,"duration":3},"国常会部署六张网建设并审议知识产权规划":{"trend":"stable","curr_rank":4,"prev_rank":4,"rise":0,"duration":3},"习近平出席世界人工智能大会宣布成立WAICO":{"trend":"stable","curr_rank":5,"prev_rank":5,"rise":0,"duration":3},"月之暗面发布全球最大开源模型Kimi K3":{"trend":"stable","curr_rank":6,"prev_rank":6,"rise":0,"duration":3},"韩国暂停个股杠杆ETF上市以遏制股市剧烈波动":{"trend":"stable","curr_rank":7,"prev_rank":7,"rise":0,"duration":3},"台湾朝野加速推动食安法修法":{"trend":"stable","curr_rank":8,"prev_rank":8,"rise":0,"duration":3},"世界杯决赛后阿根廷西班牙球员大规模冲突 国际足联调查":{"trend":"stable","curr_rank":9,"prev_rank":9,"rise":0,"duration":3},"泰国总理阿努廷访华达成多项合作成果":{"trend":"stable","curr_rank":10,"prev_rank":10,"rise":0,"duration":3}},"mktnews":{"Boeing (BA.N) engineers' union contract expires on Oct. 6.":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"Union sources said Boeing (BA.N) reached a tentative contract agreement with the engineers' union.":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"Trump, on USMCA negotiations, said he will wait until an agreement is reached with Canada and Mexico.":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"Two security sources said Iraq ordered the closure of the Shalamcheh border crossing with Iran as a precaution following a recent attack on Saudi Arabia.":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"Next round of Israel-Lebanon talks postponed to October":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"U.S. President Trump said he was not happy about Google (GOOG.O) investing to build an AI center in Finland.":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"Sources say ANTHROPIC is negotiating to secure NVIDIA (NVDA.O) as an anchor investor for an IPO that could be the largest on record. NVIDIA is reportedly considering an investment of up to $10 billion in the offering.":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"BAGHAEI, Iranian foreign ministry spokesperson, said the U.S. defense secretary's 9/11 anniversary narrative on terrorism is fundamentally contradictory; the U.S. cannot wage wars, carry out strikes and attack civilians while claiming to combat and define terrorism.":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"IRGC-affiliated Sepahnews reported Saudi-backed mercenaries were defeated by Yemen's Houthi forces and forced to retreat and flee the Marib region.":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"Drone strike from Iraq direction hits Saudi oil pipeline; Iraqi PM orders emergency probe":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"Saudi civil defense issued an early warning in Sharurah to warn of a potential danger.":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"CHINA departs Beijing for New Delhi to attend 18th BRICS leaders' meeting":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"Putin says European troop deployment to Ukraine would amount to war with Russia":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"Iraq dismisses Maysan operations commander, opens probe after attack on Saudi":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"Crude ETF holdings: WTI exposure falls for second straight day":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"DeepSeek begins limited test of AI voice dialogue with four voice options":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"CCPIT vice chairman Li Qingshuang leads Chinese business delegation to India for BRICS Business Forum":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"Pezeshkian asks who are the terrorists, rejects US and Israel pressure":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"Saudi civil defense says danger alert for Sharurah lifted.":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1}},"douban":{"求救信号":{"trend":"stable","curr_rank":1,"prev_rank":1,"rise":0,"duration":3},"特立独行":{"trend":"stable","curr_rank":2,"prev_rank":2,"rise":0,"duration":3},"战时离婚指南":{"trend":"stable","curr_rank":3,"prev_rank":3,"rise":0,"duration":3},"夜巡毒枭":{"trend":"stable","curr_rank":4,"prev_rank":4,"rise":0,"duration":3},"一直在这里":{"trend":"stable","curr_rank":5,"prev_rank":5,"rise":0,"duration":3},"抓特务":{"trend":"stable","curr_rank":6,"prev_rank":6,"rise":0,"duration":3},"怒之杀":{"trend":"stable","curr_rank":7,"prev_rank":7,"rise":0,"duration":3},"夜王":{"trend":"stable","curr_rank":8,"prev_rank":8,"rise":0,"duration":3},"激情邀约":{"trend":"stable","curr_rank":9,"prev_rank":9,"rise":0,"duration":3},"耳语者":{"trend":"stable","curr_rank":10,"prev_rank":10,"rise":0,"duration":3}},"tieba":{"反转!男子编造资助闹剧被刑拘":{"trend":"stable","curr_rank":1,"prev_rank":1,"rise":0,"duration":3},"误会!荣耀耽误抢救当事人澄清":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"骂汉族挑对立,宋剑仁被判刑":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"打假网红“铁头”一审判8年":{"trend":"stable","curr_rank":4,"prev_rank":5,"rise":1,"duration":3},"3岁男童遭4小孩围殴,已和解":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"台湾博主造谣迪士尼后秒怂":{"trend":"stable","curr_rank":6,"prev_rank":7,"rise":1,"duration":3},"刘青松已从LGD大名单移除":{"trend":"stable","curr_rank":7,"prev_rank":6,"rise":-1,"duration":3},"配苹果不配鸿蒙,网易UU挨喷":{"trend":"stable","curr_rank":8,"prev_rank":8,"rise":0,"duration":3},"偷吃token,大肥鱼工作时唱歌":{"trend":"stable","curr_rank":9,"prev_rank":9,"rise":0,"duration":3},"圣人遗骨上前线,俄军太有活":{"trend":"stable","curr_rank":10,"prev_rank":10,"rise":0,"duration":3}},"hupu":{"四岁男童”摸臀事件”的诬告方开始表演了":{"trend":"stable","curr_rank":1,"prev_rank":1,"rise":0,"duration":3},"我来做个反动派，没人觉得刘翔自己有问题吗":{"trend":"stable","curr_rank":3,"prev_rank":4,"rise":1,"duration":3},"4岁男童被指摸臀后续：女生被扒底朝天，央媒下场，退路彻底没了":{"trend":"stable","curr_rank":2,"prev_rank":2,"rise":0,"duration":3},"目前已经年龄不小但仍处于脱产状态的朋友们可以认真阅读一下":{"trend":"stable","curr_rank":4,"prev_rank":7,"rise":3,"duration":3},"为啥去香港要通行证，他们来大陆不用？":{"trend":"stable","curr_rank":6,"prev_rank":3,"rise":-3,"duration":3},"美国这套制度真不给穷人留活路，真不敢相信，这还是发达国家吗":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"篮球平行时空王朝模式开发者更新日志，玩家聊天室":{"trend":"stable","curr_rank":8,"prev_rank":6,"rise":-2,"duration":3},"马来亚大学回应称将会采取必要措施":{"trend":"stable","curr_rank":10,"prev_rank":9,"rise":-1,"duration":3},"百万网红“勇哥”开店翻车，网友痛骂“快餐刺客”":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"刘翔买断费49.4万，2015年至今工资98万+全捐，这是不是说明确实有在拿工资？":{"trend":"falling","curr_rank":10,"prev_rank":5,"rise":-5,"duration":3},"理记：刘翔要是自由，要的是特权，给了他一大堆领导岗位，还都是领导岗位，他都不干":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1}},"steam":{"Counter-Strike 2":{"trend":"stable","curr_rank":1,"prev_rank":1,"rise":0,"duration":3},"Dota 2":{"trend":"stable","curr_rank":2,"prev_rank":2,"rise":0,"duration":3},"WARDOGS":{"trend":"stable","curr_rank":3,"prev_rank":4,"rise":1,"duration":3},"Valheim":{"trend":"stable","curr_rank":4,"prev_rank":8,"rise":4,"duration":3},"FiveM":{"trend":"stable","curr_rank":6,"prev_rank":7,"rise":1,"duration":3},"Marvel Rivals":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"Bongo Cat":{"trend":"stable","curr_rank":8,"prev_rank":6,"rise":-2,"duration":3},"PUBG: BATTLEGROUNDS":{"trend":"stable","curr_rank":7,"prev_rank":3,"rise":-4,"duration":3},"Tom Clancy's Rainbow Six Siege":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"Palworld":{"trend":"stable","curr_rank":10,"prev_rank":10,"rise":0,"duration":3}},"iqiyi":{"深渊无间":{"trend":"stable","curr_rank":1,"prev_rank":1,"rise":0,"duration":3},"生逢其时":{"trend":"stable","curr_rank":2,"prev_rank":2,"rise":0,"duration":3},"大哥小助理":{"trend":"stable","curr_rank":3,"prev_rank":3,"rise":0,"duration":3},"醒来":{"trend":"stable","curr_rank":4,"prev_rank":4,"rise":0,"duration":3},"出入平安":{"trend":"stable","curr_rank":5,"prev_rank":9,"rise":4,"duration":3},"重案六组：消失的警号":{"trend":"stable","curr_rank":6,"prev_rank":5,"rise":-1,"duration":3},"喜剧之王单口季第3季":{"trend":"stable","curr_rank":7,"prev_rank":6,"rise":-1,"duration":3},"重器":{"trend":"stable","curr_rank":8,"prev_rank":7,"rise":-1,"duration":3},"说唱巅峰对决2026":{"trend":"stable","curr_rank":9,"prev_rank":8,"rise":-1,"duration":3},"师兄太稳健":{"trend":"stable","curr_rank":10,"prev_rank":10,"rise":0,"duration":3}},"qqvideo":{"兰香如故":{"trend":"stable","curr_rank":1,"prev_rank":2,"rise":1,"duration":3},"交锋":{"trend":"stable","curr_rank":2,"prev_rank":1,"rise":-1,"duration":3},"花开锦绣":{"trend":"stable","curr_rank":3,"prev_rank":3,"rise":0,"duration":3},"济公之降龙除妖":{"trend":"stable","curr_rank":4,"prev_rank":4,"rise":0,"duration":3},"百花杀":{"trend":"stable","curr_rank":5,"prev_rank":5,"rise":0,"duration":3},"囧徒之预演告别":{"trend":"stable","curr_rank":6,"prev_rank":6,"rise":0,"duration":3},"铁证":{"trend":"stable","curr_rank":7,"prev_rank":7,"rise":0,"duration":3},"爱情公寓3":{"trend":"stable","curr_rank":8,"prev_rank":8,"rise":0,"duration":3},"主角":{"trend":"stable","curr_rank":9,"prev_rank":9,"rise":0,"duration":3},"逐玉":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1}},"dongqiudi":{"埃德松-阿尔瓦雷斯：涉绑架传闻和我完全无关，已交律师处理":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"内托：带着笑容踢球是最重要的；相信在阿隆索治下能成就伟业":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"迪马济奥：帕纳辛奈科斯接近租借萨拉赫-埃丁":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"罗马诺：贝里瓦尔夏天本想离队；内托夏天时曾被热刺曼城关注":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"太阳报发文介绍巴拉德：从阿森纳弃将到桑德兰领袖":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"德媒：迪亚斯浪费机会，拜仁担忧其负荷":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"威尼斯主帅：输佛罗伦萨令人难受；布肖疑似肌肉重伤":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"曾加：格罗索曾称佛罗伦萨没法训练，但换帅球队就赢球了":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"环球体育：圣保罗、桑托斯等5队商讨限制博彩广告提案":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1},"早报：金球，自己造势":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"听说今天津门虎保级大战，去了上百国安球迷支持隔壁？":{"trend":"new","curr_rank":8,"prev_rank":null,"rise":0,"duration":1},"2026国内现场观众破4万人的足球赛已超百场，创历史新高":{"trend":"new","curr_rank":10,"prev_rank":null,"rise":0,"duration":1},"樊振东：皇马是我心中的最佳；有时候看VAR的事件太长了":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"巧合，阿莫林911当天发布会上用飞机失事打比方":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"桑德兰主帅勒布里斯：阿森纳是当前欧洲最佳球队":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"利雅得胜利官方晒C罗照片，因配文“第二，历史最佳”被误解":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"谢林汉姆：凯恩没有世界杯欧冠，只是金球陪跑者；我投罗德里":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"亚马尔20岁前欧冠已打入12球，距姆巴佩纪录仅差1球":{"trend":"new","curr_rank":1,"prev_rank":null,"rise":0,"duration":1},"拉菲尼亚达成欧冠20球只用34场，为巴西球员第三快":{"trend":"new","curr_rank":2,"prev_rank":null,"rise":0,"duration":1},"吓一大跳，库尼亚欧冠赛后遇球迷冲场突脸吓懵":{"trend":"new","curr_rank":3,"prev_rank":null,"rise":0,"duration":1},"“欧冠女王”伊娃社媒晒红裙照，她粉丝已超140万":{"trend":"new","curr_rank":4,"prev_rank":null,"rise":0,"duration":1},"热菲尼奥：中超不像大家说的那么容易踢，比赛速度比在法国快":{"trend":"new","curr_rank":5,"prev_rank":null,"rise":0,"duration":1},"自科斯塔以来，佩德罗是首位获英超月最佳球员奖的切尔西前锋":{"trend":"new","curr_rank":6,"prev_rank":null,"rise":0,"duration":1},"问题大吗？梅西训练中略感不适":{"trend":"new","curr_rank":7,"prev_rank":null,"rise":0,"duration":1},"德雷森：我对短期内解决弗罗因德续约问题充满希望":{"trend":"new","curr_rank":9,"prev_rank":null,"rise":0,"duration":1}}},"cross_platform":[],"cross_category":[],"deep_insights":{"narrative":"当前数据池呈现低活跃度特征：200份文档仅覆盖8个主题，且跨平台传播值为零。关键词缺失表明内容未形成语义焦点或议题尚未成熟。整体处于信息酝酿的潜伏期，尚未产生显著的社会或市场声量，属于早期微弱信号阶段。","causal_chains":["无关键词聚类→主题分散→跨平台复制动力不足"],"signals":[{"signal":"话题密度极低，存在信息真空","confidence":0.85},{"signal":"零跨平台传播，缺乏病毒扩散机制","confidence":0.78}],"outlook":"建议持续监控文档增长速率与关键词涌现情况。若topic_count突然攀升，可能预示议题进入爆发前夜；否则将长期维持低位静止状态。需结合外部事件触发点评估潜在活跃度拐点。"},"topic_clusters":[{"label":"projects","count":20,"items":["[RSS/dev] Tiny Website | Tiny Projects Week 0 of my year long tiny projects mission. Project 0 is building a tiny website.","[RSS/dev] How to code a tiny website | Tiny Projects How to make a tiny website that's really simple, easy to maintain, and cheap to run.","[RSS/dev] Silicon Valley Domain Names | Tiny Projects Week 1 of Tiny Projects. Exploring domain names, and how it was possible to purchase some of the biggest domain names in silicon valley, including netflix.soy.","[RSS/dev] I bought netflix.soy | Tiny Projects An exploration into top level domains. How I ended up buying netflix.soy and domains from facebook, microsoft and google.","[RSS/dev] Building a Battle Royale game | Tiny Projects How I built and launched a tiny battle royale game in the space of two weeks. It was a struggle. Welcome to week 2/3 of Tiny Projects!","[RSS/dev] One Item Store | Tiny Projects The story of building and launching a tiny online store builder called; basically think of a micro-Shopify. This is week 4/5 of Tiny Projects.","[RSS/dev] Snormal | Tiny Projects How I built Snormal: a social network for all the bits of content that don't make it onto your social media highlight reel.","[RSS/dev] I Sell Usernames on the Internet | Tiny Projects This month I built and launched a website called Earlyname, which lets you claim your original “OG” username on new apps, games and websites (for example @ben, @mike or @mia). This is the story of how it went.","[RSS/dev] Six months of Tiny Projects | Tiny Projects In this post I'll give an update on how my Tiny Projects are performing six months on, and the pros and cons of launching micro-businesses.","[RSS/dev] Selling a Tiny Project | Tiny Projects How I sold my tiny online store builder One Item Store, and how I think anyone can sell their tiny projects online.","[RSS/dev] Mailoji: I Bought 300 Emoji Domain Names From Kazakhstan and Built an Email Service | Tiny Projects I bought 300 emoji domain names from Kazakhstan and built an emoji email address service. In the process I went viral on Tik Tok, made $1000 in a week, hired a Japanese voice actor, and learnt about the weird world of emoji domains.","[RSS/dev] Selling Tiny Internet Projects For Fun and Profit | Tiny Projects How I sold my project Earlyname, how much I sold it for, and how to sell tiny internet projects.","[RSS/dev] I blew $720 on 100 notebooks from Alibaba and started a Paper Website business | Tiny Projects I started a business that lets you build websites using pen and paper. In the process I went viral on Twitter, made $1,000 in two days, and blew $720 on 100 paper notebooks from Alibaba.","[RSS/dev] I Spent 2 years Launching Tiny Projects | Tiny Projects An update on everything I've launched over 2 years, and what I've learnt about building these tiny internet projects.","[RSS/dev] Why Developers Are Building So Many Side Projects | Tiny Projects I wrote a piece for a16z Future about the trend of developers building lots of side projects instead of just one.","[RSS/tech] 4 engineering patterns behind the strongest AI Agents Challenge submissions The recent Google for Startups AI Agents Challenge revealed that the most successful multi-agent systems rely on foundational software engineering patterns rather than just raw model power. Winning architectures consistently implemented bidirectional MCP for seamless inter-agent communication, async","[RSS/tech] Decoding cosmic signals with deep learning and Keras Astroparticle physics sits at the exciting intersection of astrophysics and particle physics and stu...","[RSS/tech] Enterprise-Grade Precision for Long-Context Multimodal Embedding Inference on Cloud TPU Google Cloud has natively integrated TPU support into the vLLM serving engine, allowing developers to elastically scale high-demand embedding pipelines using Google Kubernetes Engine (GKE). To handle massive 15K+ token contexts for models like Qwen3-Embedding-8B, the engineering team implemented TPU","[RSS/tech] How to Evaluate Live & Voice Agents in ADK Moving live voice agents from demo to production requires rigorous, automated testing to handle the unpredictability of real multi-turn conversations. ADK now provides native live evaluation, allowing developers to test graph-based agent workflows against LLM-driven simulated users that generate act","[RSS/tech] Build zero-trust AI agents with Google's Agent Development Kit Building autonomous AI agents that mutate production state requires moving beyond soft system prompts to a robust zero-trust architecture. To secure Google Agent Development Kit (ADK) workflows against prompt injections and malicious execution, developers must implement hardware-backed cryptographic"]},{"label":"developers","count":14,"items":["[RSS/tech] HeyGen x Google Cloud: Bringing Avatar IV to TPUs HeyGen ported their 18B+ parameter Avatar IV video generation model to Google Cloud's Trillium (v6e) TPUs via torchax and XLA, utilizing FSDP and Ulysses sequence parallelism across an eight-chip mesh. To achieve a 1.86x speedup for real-time streaming, the engineering team pipelined exposed all-to-","[RSS/tech] Introducing Credentio: Open Source C++ Library for C2PA Content Credentials from Google Credentio is a newly released, open-source C++ library from Google that allows developers to integrate high-performance, local-first validation of C2PA Content Credentials into their client and server applications. By processing assets entirely locally with a highly optimized memory footprint, the l","[RSS/tech] Why Go is an Ideal Language for AI-Assisted Software Engineering As AI coding assistants shift the developer's primary role from writing boilerplate to reviewing and maintaining systems, language choice becomes critical for long-term architectural integrity. Go directly addresses this new paradigm by utilizing its strict compiler, integrated toolchain, and uncomp","[RSS/tech] Mastering Edge AI on Raspberry Pi with LiteRT and Gemma Deploying secure, real-time Edge AI on Raspberry Pi is now simplified using LiteRT and lightweight Gemma open models. LiteRT optimizes CPU and GPU performance, delivering fast token speeds for models like Gemma4, enabling real-time local reasoning for robotics. Developers can quickly convert, quanti","[RSS/tech] Agent Plugins package your skills, tools, and more Agent Plugins 1.0.0 is a new, vendor-neutral directory specification—backed by Google, Amazon, Microsoft, and others—for packaging Agent Skills and MCP servers into a single portable unit. By standardizing the manifest (plugin.json) and utilizing a fixed directory layout, it eliminates the need for","[RSS/tech] Scaling AI Agent Infrastructure with the MCP Stateless updates The 2026-07-28 Model Context Protocol (MCP) specification replaces legacy stateful constraints with a fully stateless core, enabling cloud-native horizontal scaling, serverless deployments, and standard round-robin load balancing. This architectural shift introduces standardized HTTP headers for eff","[RSS/tech] Model routing with Google Cloud API Gateway Google Cloud API Gateway now offers a model routing feature in Public Preview, allowing developers to dynamically route traffic to models like Gemini, Claude, or OpenAI OSS-GPT without hardcoding endpoints or managing open-source proxies. Developers can easily configure these routing rules directly","[RSS/tech] Scaling real-time AI agents with session-aware load balancing Real-time AI agents break traditional request-response load balancing paradigms because they rely on long-lived, stateful bidirectional streams that obscure true server capacity. To solve this, developers must implement application-level session tracking directly within the runtime to accurately mea","[RSS/tech] Enable on-demand expertise with Agent Skills in Genkit Go To prevent context window bloat and reduce token consumption, Genkit Go introduces Agent Skills based on a progressive disclosure architecture. Developers can package specialized instructions, scripts, and references into modular SKILL.md bundles where only the frontmatter metadata is initially expo","[RSS/tech] Agent and Model Evaluations in Gemini Enterprise Agent Platform are now GA Agent Platform's evaluation service is now generally available, providing developers with a unified engine to measure agent quality consistently across local development experiments and live production traffic. You can evaluate agents using over 20 pre-built metrics, DeepMind-backed adaptive rubrics","[RSS/tech] Run Ray on TPU, Part 2: Ray AI libraries This second installment explores how Ray’s higher-level libraries—Serve, Data, and Train—abstract the complexities of running AI workloads on Google's TPU slices. Ray Serve uses a simple topology configuration to correctly gang-schedule large multi-host models, while Ray Data eliminates data-loading","[RSS/tech] Scaling Agentic RL: High-Throughput Agentic Training with Tunix Tunix is Google’s new JAX-native post-training library designed to eliminate TPU idling bottlenecks when training multi-turn, tool-using LLM reasoning agents. It maximizes hardware throughput by combining highly concurrent, asynchronous rollouts with a decoupled producer-consumer pipeline, ensuring","[RSS/tech] Run Ray on TPU, Part 1: The foundations Ray 2.55 introduces official, first-class support for Google Cloud TPUs, enabling developers to run distributed Python workloads on Google's accelerators using the familiar Ray task-and-actor APIs. To handle the strict networking requirement of keeping multi-host TPU \"slices\" together over their Int","[RSS/tech] Building scalable AI agents with modular prompt transpilation To resolve the scaling bottlenecks and runtime errors caused by monolithic system prompts, engineering teams should treat prompts as build artifacts by modularizing instructions into reusable templates. By running these modular \"skill files\" through a transpiler, developers can enforce static valida"]},{"label":"喷嚏图卦","count":4,"items":["[RSS/news] 【喷嚏图卦20260901】人活着不能没有肌肉","[RSS/news] 20260901图卦音频版","[RSS/news] 【喷嚏图卦20260902】数亿人冲破信息茧房感觉不舒服","[RSS/news] 【喷嚏图卦20260903】35岁办不了哦"]},{"label":"铂程的票圈","count":4,"items":["[RSS/news] 【铂程的票圈52】全世界最昂贵的盐巴盒子","[RSS/news] 【铂程的票圈50】喷嚏的新后台","[RSS/news] 【铂程的票圈54】光荣与梦想","[RSS/news] 【铂程的票圈55】亚里斯多德"]},{"label":"图卦音","count":4,"items":["[RSS/news] 20260831图卦音频版","[RSS/news] 20260830图卦音频版","[RSS/news] 20260902图卦音频版","[RSS/news] 20260903图卦音频版"]},{"label":"world","count":2,"items":["[RSS/dev] 不活成他人眼中的自己 听一个分享，有一段内容比较有意思：What people say about you and what people think about you, it comes from their view of the world, It's from their opinions and the...","[RSS/tech] How to use Google microbenchmarks for evaluating TPU performance Google's open-source TPU microbenchmark suite provides developers with granular performance metrics across Network, Compute, HBM, Host Transfer, and Attention components to validate real-world hardware capabilities. By leveraging these benchmarks to establish a Roofline model, engineers can accurate"]},{"label":"喷嚏意图","count":2,"items":["[RSS/news] 【喷嚏意图17】生活最大的优点","[RSS/news] 【喷嚏意图19】看起来彼此相连"]},{"label":"七武士：为何赢的是农","count":2,"items":["[RSS/news] 七武士：为何赢的是农民-notebooklm","[RSS/news] 公民凯恩：帝国深处的雪-notebooklm"]}],"meta":{"engine":"insight_engine","llm_provider":"agnes","llm_available":true,"index_built":false,"embed_model":"BAAI/bge-small-zh-en-v1.5","elapsed_seconds":38.41},"rss_trajectories":{"keywords":{"VDDK":{"lifecycle":"gone","first_seen":"2026-09-11T21:36:39.475058+08:00","latest_rank":null,"duration":0},"投江女子聊天记录":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"小米":{"lifecycle":"stable","first_seen":"2026-09-11T14:44:28.640410+08:00","latest_rank":null,"duration":0},"摄像头":{"lifecycle":"gone","first_seen":"2026-09-11T21:05:56.716336+08:00","latest_rank":null,"duration":0},"国产算力":{"lifecycle":"gone","first_seen":"2026-09-11T11:53:56.128439+08:00","latest_rank":null,"duration":0},"token":{"lifecycle":"gone","first_seen":"2026-09-09T20:13:36.599395+08:00","latest_rank":null,"duration":0},"表示":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"微软":{"lifecycle":"gone","first_seen":"2026-09-11T21:36:39.475058+08:00","latest_rank":null,"duration":0},"AI":{"lifecycle":"gone","first_seen":"2026-09-11T14:16:24.299809+08:00","latest_rank":null,"duration":0},"llm":{"lifecycle":"gone","first_seen":"2026-09-10T05:20:19.596559+08:00","latest_rank":null,"duration":0},"客厅":{"lifecycle":"gone","first_seen":"2026-09-11T20:29:33.375400+08:00","latest_rank":null,"duration":0},"为什么":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"原神":{"lifecycle":"stable","first_seen":"2026-09-11T20:29:33.375400+08:00","latest_rank":null,"duration":0},"考公":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"\"美团\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"\"RLVR\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"刘备孙权历史假设":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"\"日活\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"vivo":{"lifecycle":"gone","first_seen":"2026-09-11T21:53:21.861754+08:00","latest_rank":null,"duration":0},"ai":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"兰州大学拉练":{"lifecycle":"gone","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"成品油价格":{"lifecycle":"gone","first_seen":"2026-09-11T15:26:25.945766+08:00","latest_rank":null,"duration":0},"CLAUDE":{"lifecycle":"gone","first_seen":"2026-09-11T17:12:09.176349+08:00","latest_rank":null,"duration":0},"网易":{"lifecycle":"gone","first_seen":"2026-09-11T14:29:56.707096+08:00","latest_rank":null,"duration":0},"\"男篮\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"正在":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"索尼":{"lifecycle":"gone","first_seen":"2026-09-11T21:36:39.475058+08:00","latest_rank":null,"duration":0},"智能":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"滕王阁序":{"lifecycle":"gone","first_seen":"2026-09-11T14:29:56.707096+08:00","latest_rank":null,"duration":0},"零钱通余额宝付款":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"A股":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"三星嘲讽苹果":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"via":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"AI研发":{"lifecycle":"gone","first_seen":"2026-09-11T20:05:51.620896+08:00","latest_rank":null,"duration":0},"zhihu":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"助学资助反转":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"公告类":{"lifecycle":"gone","first_seen":"2026-09-10T05:20:19.596559+08:00","latest_rank":null,"duration":0},"荣耀":{"lifecycle":"gone","first_seen":"2026-09-11T14:29:56.707096+08:00","latest_rank":null,"duration":0},"址  ":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"算力":{"lifecycle":"gone","first_seen":"2026-09-11T14:16:24.299809+08:00","latest_rank":null,"duration":0},"news":{"lifecycle":"gone","first_seen":"2026-09-09T07:04:55.998030+08:00","latest_rank":null,"duration":0},"自己":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"刘禹锡":{"lifecycle":"stable","first_seen":"2026-09-12T09:37:20.169402+08:00","latest_rank":null,"duration":0},"Embedding":{"lifecycle":"gone","first_seen":"2026-09-11T14:16:24.299809+08:00","latest_rank":null,"duration":0},"铁头":{"lifecycle":"stable","first_seen":"2026-09-11T17:12:09.176349+08:00","latest_rank":null,"duration":0},"中国客厅变化":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"武汉小学":{"lifecycle":"gone","first_seen":"2026-09-11T18:07:37.122508+08:00","latest_rank":null,"duration":0},"\"短剧\",":{"lifecycle":"gone","first_seen":"2026-09-11T16:53:35.498647+08:00","latest_rank":null,"duration":0},"F1":{"lifecycle":"stable","first_seen":"2026-09-12T09:05:34.797697+08:00","latest_rank":null,"duration":0},"正脸":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"荣耀手表6 Pro":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"花少5好评":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"人类人口结构":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"ACL 2026":{"lifecycle":"gone","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"微信":{"lifecycle":"gone","first_seen":"2026-09-11T11:07:21.704427+08:00","latest_rank":null,"duration":0},"巩立姣":{"lifecycle":"gone","first_seen":"2026-09-11T21:36:39.475058+08:00","latest_rank":null,"duration":0},"杭州领克车辆火情":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"百度":{"lifecycle":"gone","first_seen":"2026-09-11T21:53:21.861754+08:00","latest_rank":null,"duration":0},"万亿参数模型":{"lifecycle":"gone","first_seen":"2026-09-11T14:29:56.707096+08:00","latest_rank":null,"duration":0},"贝赫和斯维纳通-戴尔猜想":{"lifecycle":"gone","first_seen":"2026-09-11T11:07:21.704427+08:00","latest_rank":null,"duration":0},"铁头一审获刑8年":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"预训练":{"lifecycle":"gone","first_seen":"2026-09-11T14:16:24.299809+08:00","latest_rank":null,"duration":0},"iPhone 18 Pro":{"lifecycle":"gone","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"deepseek":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"中国女篮":{"lifecycle":"gone","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"氢能储运":{"lifecycle":"gone","first_seen":"2026-09-11T20:29:33.375400+08:00","latest_rank":null,"duration":0},"朝日新":{"lifecycle":"gone","first_seen":"2026-09-10T02:05:52.491743+08:00","latest_rank":null,"duration":0},"问题":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"香蕉地农药":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"V4":{"lifecycle":"gone","first_seen":"2026-09-11T21:05:56.716336+08:00","latest_rank":null,"duration":0},"爱马仕宠物包":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"ithome":{"lifecycle":"gone","first_seen":"2026-09-11T21:53:21.861754+08:00","latest_rank":null,"duration":0},"苏轼":{"lifecycle":"stable","first_seen":"2026-09-12T09:37:20.169402+08:00","latest_rank":null,"duration":0},"nbdnews":{"lifecycle":"gone","first_seen":"2026-09-09T07:42:07.468657+08:00","latest_rank":null,"duration":0},"VMware":{"lifecycle":"gone","first_seen":"2026-09-11T21:36:39.475058+08:00","latest_rank":null,"duration":0},"Georgetown":{"lifecycle":"gone","first_seen":"2026-09-11T11:07:21.704427+08:00","latest_rank":null,"duration":0},"红果短剧日活":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"中俄伊塞四国UP主":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"Navier-Stokes":{"lifecycle":"gone","first_seen":"2026-09-11T21:36:39.475058+08:00","latest_rank":null,"duration":0},"曼联":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"麒麟芯片":{"lifecycle":"stable","first_seen":"2026-09-12T09:05:34.797697+08:00","latest_rank":null,"duration":0},"系统":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"父母":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"agi":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"热搜":{"lifecycle":"gone","first_seen":"2026-09-11T15:26:25.945766+08:00","latest_rank":null,"duration":0},"烽火职业联赛":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"\"语义表征\",":{"lifecycle":"gone","first_seen":"2026-09-11T16:53:35.498647+08:00","latest_rank":null,"duration":0},"库克":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"DeepSeek":{"lifecycle":"stable","first_seen":"2026-09-11T21:05:56.716336+08:00","latest_rank":null,"duration":0},"Bilibili":{"lifecycle":"gone","first_seen":"2026-09-11T21:53:21.861754+08:00","latest_rank":null,"duration":0},"Netfli":{"lifecycle":"gone","first_seen":"2026-09-11T11:53:56.128439+08:00","latest_rank":null,"duration":0},"大模型":{"lifecycle":"gone","first_seen":"2026-09-11T14:16:24.299809+08:00","latest_rank":null,"duration":0},"宣布":{"lifecycle":"gone","first_seen":"2026-09-09T09:09:33.838171+08:00","latest_rank":null,"duration":0},"千亿参数":{"lifecycle":"gone","first_seen":"2026-09-11T15:26:25.945766+08:00","latest_rank":null,"duration":0},"小米SU7":{"lifecycle":"gone","first_seen":"2026-09-11T18:07:37.122508+08:00","latest_rank":null,"duration":0},"丁禹兮":{"lifecycle":"stable","first_seen":"2026-09-12T09:05:34.797697+08:00","latest_rank":null,"duration":0},"WBG解约":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"github":{"lifecycle":"gone","first_seen":"2026-09-09T07:42:07.468657+08:00","latest_rank":null,"duration":0},"apple":{"lifecycle":"gone","first_seen":"2026-09-10T05:20:19.596559+08:00","latest_rank":null,"duration":0},"claude":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"九尾妖狐":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"徽章按斤卖":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"川西秋天":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"v4":{"lifecycle":"gone","first_seen":"2026-09-10T16:13:10.222433+08:00","latest_rank":null,"duration":0},"日本签证":{"lifecycle":"gone","first_seen":"2026-09-11T15:26:25.945766+08:00","latest_rank":null,"duration":0},"LongCat":{"lifecycle":"stable","first_seen":"2026-09-11T14:16:24.299809+08:00","latest_rank":null,"duration":0},"美团":{"lifecycle":"stable","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"育碧":{"lifecycle":"gone","first_seen":"2026-09-11T21:36:39.475058+08:00","latest_rank":null,"duration":0},"刀郎":{"lifecycle":"declining","first_seen":"2026-09-11T21:53:21.861754+08:00","latest_rank":null,"duration":0},"深海科考":{"lifecycle":"gone","first_seen":"2026-09-11T14:29:56.707096+08:00","latest_rank":null,"duration":0},"罗贝里":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"训练":{"lifecycle":"gone","first_seen":"2026-09-11T14:16:24.299809+08:00","latest_rank":null,"duration":0},"\"红果\",":{"lifecycle":"gone","first_seen":"2026-09-11T16:53:35.498647+08:00","latest_rank":null,"duration":0},"机器":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"什么":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"时间":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"老人儿童":{"lifecycle":"gone","first_seen":"2026-09-11T14:44:28.640410+08:00","latest_rank":null,"duration":0},"赴港追星取消低保":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"中国男篮":{"lifecycle":"gone","first_seen":"2026-09-11T15:26:25.945766+08:00","latest_rank":null,"duration":0},"华为麒麟9050Pro":{"lifecycle":"stable","first_seen":"2026-09-12T09:37:20.169402+08:00","latest_rank":null,"duration":0},"LongCat稀疏注意力":{"lifecycle":"gone","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"\"红果短剧\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"周杰伦":{"lifecycle":"gone","first_seen":"2026-09-11T14:29:56.707096+08:00","latest_rank":null,"duration":0},"安全":{"lifecycle":"gone","first_seen":"2026-09-09T07:42:07.468657+08:00","latest_rank":null,"duration":0},"韦世豪遭重罚":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"Kimi":{"lifecycle":"stable","first_seen":"2026-09-12T09:05:34.797697+08:00","latest_rank":null,"duration":0},"\"Agentic Coding\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"LoRA":{"lifecycle":"declining","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"科技":{"lifecycle":"gone","first_seen":"2026-09-10T04:16:48.245394+08:00","latest_rank":null,"duration":0},"chatgpt":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"LVMH":{"lifecycle":"stable","first_seen":"2026-09-12T09:37:20.169402+08:00","latest_rank":null,"duration":0},"短剧":{"lifecycle":"gone","first_seen":"2026-09-11T11:53:56.128439+08:00","latest_rank":null,"duration":0},"大连小学正装":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"周星驰配角NPC":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"baidu":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"日本暴雨":{"lifecycle":"gone","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"世界":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"https":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"乡村振兴":{"lifecycle":"gone","first_seen":"2026-09-11T21:05:56.716336+08:00","latest_rank":null,"duration":0},"\"LongCat\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"日本签证规费上调":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"扫地机器人":{"lifecycle":"gone","first_seen":"2026-09-11T21:05:56.716336+08:00","latest_rank":null,"duration":0},"item":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"做饭教程":{"lifecycle":"gone","first_seen":"2026-09-11T20:29:33.375400+08:00","latest_rank":null,"duration":0},"hk01":{"lifecycle":"gone","first_seen":"2026-09-10T04:16:48.245394+08:00","latest_rank":null,"duration":0},"id":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"AI Agent":{"lifecycle":"declining","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"中国客厅":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"HackerNews":{"lifecycle":"gone","first_seen":"2026-09-11T21:53:21.861754+08:00","latest_rank":null,"duration":0},"知乎":{"lifecycle":"gone","first_seen":"2026-09-11T21:53:21.861754+08:00","latest_rank":null,"duration":0},"\"KDD\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"聚类":{"lifecycle":"gone","first_seen":"2026-09-11T14:16:24.299809+08:00","latest_rank":null,"duration":0},"\"万亿参数\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"多模态大模型":{"lifecycle":"gone","first_seen":"2026-09-11T13:07:58.333254+08:00","latest_rank":null,"duration":0},"\"库克\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"铁头获刑":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"域名":{"lifecycle":"gone","first_seen":"2026-09-11T11:53:56.128439+08:00","latest_rank":null,"duration":0},"男子编造催资助":{"lifecycle":"gone","first_seen":"2026-09-11T20:29:33.375400+08:00","latest_rank":null,"duration":0},"白敬亭":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"文章网":{"lifecycle":"gone","first_seen":"2026-09-09T07:42:07.468657+08:00","latest_rank":null,"duration":0},"推荐":{"lifecycle":"gone","first_seen":"2026-09-11T14:16:24.299809+08:00","latest_rank":null,"duration":0},"已经":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"公益":{"lifecycle":"gone","first_seen":"2026-09-11T21:05:56.716336+08:00","latest_rank":null,"duration":0},"bilibili":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"ACL":{"lifecycle":"gone","first_seen":"2026-09-11T14:16:24.299809+08:00","latest_rank":null,"duration":0},"搜索":{"lifecycle":"gone","first_seen":"2026-09-11T11:07:21.704427+08:00","latest_rank":null,"duration":0},"三体2":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"携程杀熟":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"google":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"RAG":{"lifecycle":"gone","first_seen":"2026-09-11T11:07:21.704427+08:00","latest_rank":null,"duration":0},"官方通报":{"lifecycle":"gone","first_seen":"2026-09-11T20:29:33.375400+08:00","latest_rank":null,"duration":0},"dev":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"Top论文":{"lifecycle":"gone","first_seen":"2026-09-11T14:16:24.299809+08:00","latest_rank":null,"duration":0},"三农":{"lifecycle":"gone","first_seen":"2026-09-11T21:05:56.716336+08:00","latest_rank":null,"duration":0},"\"BSD猜想\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"\"iPhone 17 Pro\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"氢能":{"lifecycle":"gone","first_seen":"2026-09-11T21:36:39.475058+08:00","latest_rank":null,"duration":0},"胡塞武装":{"lifecycle":"stable","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"荣耀魔法画报":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"美联储":{"lifecycle":"gone","first_seen":"2026-09-11T17:12:09.176349+08:00","latest_rank":null,"duration":0},"前置摄像头保护眼睛":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"评测基准":{"lifecycle":"gone","first_seen":"2026-09-11T15:26:25.945766+08:00","latest_rank":null,"duration":0},"美团LongCat-2.0":{"lifecycle":"stable","first_seen":"2026-09-12T09:37:20.169402+08:00","latest_rank":null,"duration":0},"上下文":{"lifecycle":"gone","first_seen":"2026-09-11T14:16:24.299809+08:00","latest_rank":null,"duration":0},"皮鞋手表西装酒行业崩溃":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"反诈":{"lifecycle":"gone","first_seen":"2026-09-11T13:07:58.333254+08:00","latest_rank":null,"duration":0},"cnn":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"心梗120":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"携程":{"lifecycle":"gone","first_seen":"2026-09-11T14:44:28.640410+08:00","latest_rank":null,"duration":0},"离婚":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"王者荣耀":{"lifecycle":"gone","first_seen":"2026-09-11T14:44:28.640410+08:00","latest_rank":null,"duration":0},"\"算力集群\",":{"lifecycle":"gone","first_seen":"2026-09-11T16:53:35.498647+08:00","latest_rank":null,"duration":0},"微信漏洞":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"网红":{"lifecycle":"stable","first_seen":"2026-09-12T09:37:20.169402+08:00","latest_rank":null,"duration":0},"市场":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"贝赫猜想":{"lifecycle":"gone","first_seen":"2026-09-11T11:53:56.128439+08:00","latest_rank":null,"duration":0},"公司":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"模型":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"这个":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"\"OpenAI\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"RLVR":{"lifecycle":"declining","first_seen":"2026-09-11T11:07:21.704427+08:00","latest_rank":null,"duration":0},"打假":{"lifecycle":"gone","first_seen":"2026-09-11T21:05:56.716336+08:00","latest_rank":null,"duration":0},"文 ·":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"谭松韵":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"新能源汽车":{"lifecycle":"gone","first_seen":"2026-09-11T21:05:56.716336+08:00","latest_rank":null,"duration":0},"资助争议":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"评论网":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"muse":{"lifecycle":"gone","first_seen":"2026-09-09T16:14:33.793016+08:00","latest_rank":null,"duration":0},"低保户空调":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"开学":{"lifecycle":"stable","first_seen":"2026-09-12T09:05:34.797697+08:00","latest_rank":null,"duration":0},"可能":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"成品油价格调控":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"馄饨28元限量":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"关税":{"lifecycle":"stable","first_seen":"2026-09-12T09:37:20.169402+08:00","latest_rank":null,"duration":0},"老人儿童人口比例":{"lifecycle":"gone","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"刀郎徐子尧":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"影视飓风":{"lifecycle":"gone","first_seen":"2026-09-11T14:44:28.640410+08:00","latest_rank":null,"duration":0},"杀熟":{"lifecycle":"gone","first_seen":"2026-09-11T18:07:37.122508+08:00","latest_rank":null,"duration":0},"家庭客厅":{"lifecycle":"gone","first_seen":"2026-09-11T13:07:58.333254+08:00","latest_rank":null,"duration":0},"农民旅游":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"arxiv":{"lifecycle":"gone","first_seen":"2026-09-10T05:20:19.596559+08:00","latest_rank":null,"duration":0},"莱巴金娜":{"lifecycle":"gone","first_seen":"2026-09-11T11:53:56.128439+08:00","latest_rank":null,"duration":0},"北海造船厂":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"\"AI Agent\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"了  ":{"lifecycle":"gone","first_seen":"2026-09-11T04:09:50.742364+08:00","latest_rank":null,"duration":0},"cn_tech":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"伊朗":{"lifecycle":"declining","first_seen":"2026-09-12T09:05:34.797697+08:00","latest_rank":null,"duration":0},"watch":{"lifecycle":"gone","first_seen":"2026-09-10T11:12:41.474817+08:00","latest_rank":null,"duration":0},"华为":{"lifecycle":"stable","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"葫芦爷爷":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"张家齐妈妈":{"lifecycle":"gone","first_seen":"2026-09-11T20:29:33.375400+08:00","latest_rank":null,"duration":0},"发布会":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"美军航母":{"lifecycle":"stable","first_seen":"2026-09-12T09:37:20.169402+08:00","latest_rank":null,"duration":0},"鸿蒙":{"lifecycle":"gone","first_seen":"2026-09-11T14:29:56.707096+08:00","latest_rank":null,"duration":0},"中国机遇":{"lifecycle":"gone","first_seen":"2026-09-11T14:44:28.640410+08:00","latest_rank":null,"duration":0},"推出":{"lifecycle":"gone","first_seen":"2026-09-10T03:05:22.377751+08:00","latest_rank":null,"duration":0},"中国军网":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"机器人":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"F1西班牙站":{"lifecycle":"gone","first_seen":"2026-09-11T14:29:56.707096+08:00","latest_rank":null,"duration":0},"学区房":{"lifecycle":"stable","first_seen":"2026-09-12T09:05:34.797697+08:00","latest_rank":null,"duration":0},"KDD 2026":{"lifecycle":"gone","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"兰香如故":{"lifecycle":"stable","first_seen":"2026-09-12T09:37:20.169402+08:00","latest_rank":null,"duration":0},"可以":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"原神六周年":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"120误触魔法画报":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"花少8":{"lifecycle":"gone","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"Agentic RL":{"lifecycle":"gone","first_seen":"2026-09-11T11:53:56.128439+08:00","latest_rank":null,"duration":0},"RSS":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"修仙小说":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"人工":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"\"图灵\",":{"lifecycle":"gone","first_seen":"2026-09-11T16:53:35.498647+08:00","latest_rank":null,"duration":0},"长上下文":{"lifecycle":"gone","first_seen":"2026-09-11T20:05:51.620896+08:00","latest_rank":null,"duration":0},"家电":{"lifecycle":"gone","first_seen":"2026-09-11T21:05:56.716336+08:00","latest_rank":null,"duration":0},"皮鞋":{"lifecycle":"gone","first_seen":"2026-09-11T20:29:33.375400+08:00","latest_rank":null,"duration":0},"支付宝":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"油价":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"张雪":{"lifecycle":"gone","first_seen":"2026-09-11T21:36:39.475058+08:00","latest_rank":null,"duration":0},"LG":{"lifecycle":"gone","first_seen":"2026-09-11T21:05:56.716336+08:00","latest_rank":null,"duration":0},"astra":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"Google":{"lifecycle":"gone","first_seen":"2026-09-11T21:36:39.475058+08:00","latest_rank":null,"duration":0},"openai":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"雷军":{"lifecycle":"stable","first_seen":"2026-09-12T09:05:34.797697+08:00","latest_rank":null,"duration":0},"助学生质问":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"考古文物失踪":{"lifecycle":"stable","first_seen":"2026-09-12T09:37:20.169402+08:00","latest_rank":null,"duration":0},"日本梅毒":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"杭州":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"flash":{"lifecycle":"gone","first_seen":"2026-09-09T22:18:47.449623+08:00","latest_rank":null,"duration":0},"丁俊晖":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"代码生成":{"lifecycle":"gone","first_seen":"2026-09-11T13:07:58.333254+08:00","latest_rank":null,"duration":0},"王辉":{"lifecycle":"stable","first_seen":"2026-09-12T09:05:34.797697+08:00","latest_rank":null,"duration":0},"iphone":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"小学罚站":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"国产算力集群":{"lifecycle":"gone","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"GitHub":{"lifecycle":"gone","first_seen":"2026-09-11T21:53:21.861754+08:00","latest_rank":null,"duration":0},"aihot":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"糖尿病患者人数":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"我们":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"保护眼睛":{"lifecycle":"gone","first_seen":"2026-09-11T20:29:33.375400+08:00","latest_rank":null,"duration":0},"中美":{"lifecycle":"stable","first_seen":"2026-09-12T09:37:20.169402+08:00","latest_rank":null,"duration":0},"KDD":{"lifecycle":"gone","first_seen":"2026-09-11T14:16:24.299809+08:00","latest_rank":null,"duration":0},"vivo X500 Pro Max":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"iPhone18Pro":{"lifecycle":"gone","first_seen":"2026-09-11T21:05:56.716336+08:00","latest_rank":null,"duration":0},"iPhone":{"lifecycle":"gone","first_seen":"2026-09-11T13:07:58.333254+08:00","latest_rank":null,"duration":0},"员工裸奔":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"手机厂商":{"lifecycle":"gone","first_seen":"2026-09-11T21:53:21.861754+08:00","latest_rank":null,"duration":0},"老头环":{"lifecycle":"gone","first_seen":"2026-09-11T11:53:56.128439+08:00","latest_rank":null,"duration":0},"开始":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"FPX vs AQ":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"李立群吐槽AI":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"李旭双开":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"OpenAI":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"\"长上下文\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"几何体":{"lifecycle":"gone","first_seen":"2026-09-11T11:07:21.704427+08:00","latest_rank":null,"duration":0},"鬼王雷宇扬":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"汽车折叠屏":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"戒糖":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"Tiny Projects":{"lifecycle":"gone","first_seen":"2026-09-11T11:53:56.128439+08:00","latest_rank":null,"duration":0},"少数派":{"lifecycle":"gone","first_seen":"2026-09-11T21:53:21.861754+08:00","latest_rank":null,"duration":0},"一箭六星":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"孙燕姿":{"lifecycle":"gone","first_seen":"2026-09-11T21:53:21.861754+08:00","latest_rank":null,"duration":0},"折叠机":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"梅姨":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"Agent":{"lifecycle":"gone","first_seen":"2026-09-11T14:16:24.299809+08:00","latest_rank":null,"duration":0},"anthropic":{"lifecycle":"gone","first_seen":"2026-09-09T12:31:59.329469+08:00","latest_rank":null,"duration":0},"douyin":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"网址":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"人口老龄化":{"lifecycle":"gone","first_seen":"2026-09-11T13:07:58.333254+08:00","latest_rank":null,"duration":0},"香港 ":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"数据":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"智能体":{"lifecycle":"gone","first_seen":"2026-09-11T14:16:24.299809+08:00","latest_rank":null,"duration":0},"周杰伦西西里MV":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"发布":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"精神病医院更名":{"lifecycle":"gone","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"ycombinator":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"\"国产算力\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"阅读原":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"农业":{"lifecycle":"gone","first_seen":"2026-09-11T17:12:09.176349+08:00","latest_rank":null,"duration":0},"亿元 ":{"lifecycle":"gone","first_seen":"2026-09-09T07:42:07.468657+08:00","latest_rank":null,"duration":0},"一个":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"搜索排序":{"lifecycle":"gone","first_seen":"2026-09-11T14:16:24.299809+08:00","latest_rank":null,"duration":0},"\"Agentic\",":{"lifecycle":"gone","first_seen":"2026-09-11T16:53:35.498647+08:00","latest_rank":null,"duration":0},"对等原则":{"lifecycle":"stable","first_seen":"2026-09-12T09:37:20.169402+08:00","latest_rank":null,"duration":0},"智驾":{"lifecycle":"gone","first_seen":"2026-09-11T21:05:56.716336+08:00","latest_rank":null,"duration":0},"卢昱晓":{"lifecycle":"stable","first_seen":"2026-09-12T09:05:34.797697+08:00","latest_rank":null,"duration":0},"皮鞋手表西装行业崩溃":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"雷思维双开":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"电影飓风":{"lifecycle":"gone","first_seen":"2026-09-11T17:12:09.176349+08:00","latest_rank":null,"duration":0},"\"LoRA\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"多模态":{"lifecycle":"gone","first_seen":"2026-09-11T14:16:24.299809+08:00","latest_rank":null,"duration":0},"月日":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"燃油车":{"lifecycle":"gone","first_seen":"2026-09-11T14:44:28.640410+08:00","latest_rank":null,"duration":0},"旅行":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"\"搜索\",":{"lifecycle":"gone","first_seen":"2026-09-11T16:53:35.498647+08:00","latest_rank":null,"duration":0},"老年人":{"lifecycle":"gone","first_seen":"2026-09-11T17:12:09.176349+08:00","latest_rank":null,"duration":0},"西装":{"lifecycle":"gone","first_seen":"2026-09-11T20:29:33.375400+08:00","latest_rank":null,"duration":0},"前置摄像头":{"lifecycle":"gone","first_seen":"2026-09-11T20:29:33.375400+08:00","latest_rank":null,"duration":0},"天下足球":{"lifecycle":"gone","first_seen":"2026-09-11T20:29:33.375400+08:00","latest_rank":null,"duration":0},"学院":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"助学":{"lifecycle":"gone","first_seen":"2026-09-11T21:05:56.716336+08:00","latest_rank":null,"duration":0},"宿舍":{"lifecycle":"stable","first_seen":"2026-09-12T09:05:34.797697+08:00","latest_rank":null,"duration":0},"敲诈勒索":{"lifecycle":"stable","first_seen":"2026-09-12T09:37:20.169402+08:00","latest_rank":null,"duration":0},"美元":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"王者荣耀世界":{"lifecycle":"gone","first_seen":"2026-09-11T13:07:58.333254+08:00","latest_rank":null,"duration":0},"了一":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"对线追梦格林":{"lifecycle":"gone","first_seen":"2026-09-11T20:29:33.375400+08:00","latest_rank":null,"duration":0},"AHM数学家组织":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"抓人":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"G2":{"lifecycle":"stable","first_seen":"2026-09-12T09:05:34.797697+08:00","latest_rank":null,"duration":0},"洗衣机":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"折叠屏":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"\"千禧难题\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"警方通报":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"青岛火灾":{"lifecycle":"gone","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"中国驻日大使馆":{"lifecycle":"stable","first_seen":"2026-09-12T09:37:20.169402+08:00","latest_rank":null,"duration":0},"应用":{"lifecycle":"gone","first_seen":"2026-09-10T04:16:48.245394+08:00","latest_rank":null,"duration":0},"坠楼砸车":{"lifecycle":"gone","first_seen":"2026-09-11T15:26:25.945766+08:00","latest_rank":null,"duration":0},"跨省":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"月 日":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"duo":{"lifecycle":"gone","first_seen":"2026-09-10T05:20:19.596559+08:00","latest_rank":null,"duration":0},"男子编造女生催资助":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"日本":{"lifecycle":"stable","first_seen":"2026-09-11T17:12:09.176349+08:00","latest_rank":null,"duration":0},"用户":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"油价调整":{"lifecycle":"gone","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"金融强国":{"lifecycle":"gone","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"暴雨":{"lifecycle":"stable","first_seen":"2026-09-12T09:05:34.797697+08:00","latest_rank":null,"duration":0},"孙千":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"BSD猜想":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"items":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"\"AI\",":{"lifecycle":"gone","first_seen":"2026-09-11T16:53:35.498647+08:00","latest_rank":null,"duration":0},"微博":{"lifecycle":"gone","first_seen":"2026-09-11T21:53:21.861754+08:00","latest_rank":null,"duration":0},"兰州大学":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"ACL2026":{"lifecycle":"stable","first_seen":"2026-09-12T09:37:20.169402+08:00","latest_rank":null,"duration":0},"pro":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"研究":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"日韩股市":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"成品油":{"lifecycle":"gone","first_seen":"2026-09-11T21:36:39.475058+08:00","latest_rank":null,"duration":0},"MineExplorer":{"lifecycle":"gone","first_seen":"2026-09-11T11:53:56.128439+08:00","latest_rank":null,"duration":0},"三角洲职业赛":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"老狗":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"CatPaw":{"lifecycle":"gone","first_seen":"2026-09-11T11:53:56.128439+08:00","latest_rank":null,"duration":0},"千禧难题":{"lifecycle":"gone","first_seen":"2026-09-11T11:07:21.704427+08:00","latest_rank":null,"duration":0},"Token":{"lifecycle":"gone","first_seen":"2026-09-11T20:05:51.620896+08:00","latest_rank":null,"duration":0},"发射":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"\"GeoRA\",":{"lifecycle":"gone","first_seen":"2026-09-11T16:53:35.498647+08:00","latest_rank":null,"duration":0},"徐静雨追梦格林":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"1.68亿":{"lifecycle":"gone","first_seen":"2026-09-11T21:05:56.716336+08:00","latest_rank":null,"duration":0},"客厅意义":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"三体":{"lifecycle":"gone","first_seen":"2026-09-11T14:44:28.640410+08:00","latest_rank":null,"duration":0},"朱晏":{"lifecycle":"stable","first_seen":"2026-09-12T09:05:34.797697+08:00","latest_rank":null,"duration":0},"日活":{"lifecycle":"gone","first_seen":"2026-09-11T20:29:33.375400+08:00","latest_rank":null,"duration":0},"亿美元":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"中方回应":{"lifecycle":"gone","first_seen":"2026-09-11T20:29:33.375400+08:00","latest_rank":null,"duration":0},"LLM":{"lifecycle":"gone","first_seen":"2026-09-11T11:53:56.128439+08:00","latest_rank":null,"duration":0},"波士顿鲸鱼":{"lifecycle":"stable","first_seen":"2026-09-12T09:37:20.169402+08:00","latest_rank":null,"duration":0},"小米汽车":{"lifecycle":"gone","first_seen":"2026-09-11T20:29:33.375400+08:00","latest_rank":null,"duration":0},"问题 ":{"lifecycle":"gone","first_seen":"2026-09-10T02:05:52.491743+08:00","latest_rank":null,"duration":0},"雷宇扬":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"120误触":{"lifecycle":"gone","first_seen":"2026-09-11T20:29:33.375400+08:00","latest_rank":null,"duration":0},"\"Agent\",":{"lifecycle":"gone","first_seen":"2026-09-11T16:53:35.498647+08:00","latest_rank":null,"duration":0},"花少":{"lifecycle":"gone","first_seen":"2026-09-11T14:44:28.640410+08:00","latest_rank":null,"duration":0},"\"CatPaw\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"签证费":{"lifecycle":"stable","first_seen":"2026-09-12T09:37:20.169402+08:00","latest_rank":null,"duration":0},"考公失败":{"lifecycle":"gone","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"特朗普":{"lifecycle":"gone","first_seen":"2026-09-09T08:07:21.510616+08:00","latest_rank":null,"duration":0},"开源":{"lifecycle":"gone","first_seen":"2026-09-11T11:07:21.704427+08:00","latest_rank":null,"duration":0},"\"搜索排序\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"\"MineExplorer\",":{"lifecycle":"gone","first_seen":"2026-09-11T16:53:35.498647+08:00","latest_rank":null,"duration":0},"芯片":{"lifecycle":"gone","first_seen":"2026-09-10T18:08:59.966053+08:00","latest_rank":null,"duration":0},"Peter Scholze":{"lifecycle":"gone","first_seen":"2026-09-11T19:13:04.498177+08:00","latest_rank":null,"duration":0},"家庭生活":{"lifecycle":"gone","first_seen":"2026-09-11T20:29:33.375400+08:00","latest_rank":null,"duration":0},"gpt-6":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"殷桃":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"\"多模态\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"微信号":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"\"知识图谱\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"乡村":{"lifecycle":"gone","first_seen":"2026-09-11T21:36:39.475058+08:00","latest_rank":null,"duration":0},"罚站":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"小岛秀夫":{"lifecycle":"gone","first_seen":"2026-09-11T21:36:39.475058+08:00","latest_rank":null,"duration":0},"评论:":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"ChatGPT":{"lifecycle":"gone","first_seen":"2026-09-11T11:07:21.704427+08:00","latest_rank":null,"duration":0},"\"LLM\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"911事件":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"人工智能":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"MinExplorer":{"lifecycle":"gone","first_seen":"2026-09-11T20:05:51.620896+08:00","latest_rank":null,"duration":0},"三星":{"lifecycle":"gone","first_seen":"2026-09-11T21:53:21.861754+08:00","latest_rank":null,"duration":0},"视频":{"lifecycle":"gone","first_seen":"2026-09-09T05:15:06.342698+08:00","latest_rank":null,"duration":0},"LPL":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"三部门":{"lifecycle":"gone","first_seen":"2026-09-11T21:36:39.475058+08:00","latest_rank":null,"duration":0},"911事件25周年":{"lifecycle":"gone","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"杨迪":{"lifecycle":"stable","first_seen":"2026-09-12T09:05:34.797697+08:00","latest_rank":null,"duration":0},"手表":{"lifecycle":"gone","first_seen":"2026-09-11T20:29:33.375400+08:00","latest_rank":null,"duration":0},"东契奇生涯困境":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"\"评测基准\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"油价上调":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"美元 ":{"lifecycle":"gone","first_seen":"2026-09-11T06:06:43.588736+08:00","latest_rank":null,"duration":0},"苹果":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"工智能":{"lifecycle":"gone","first_seen":"2026-09-10T06:06:11.049780+08:00","latest_rank":null,"duration":0},"\"LongCat-2.0\",":{"lifecycle":"gone","first_seen":"2026-09-11T16:53:35.498647+08:00","latest_rank":null,"duration":0},"211":{"lifecycle":"stable","first_seen":"2026-09-12T09:05:34.797697+08:00","latest_rank":null,"duration":0},"不是":{"lifecycle":"gone","first_seen":"2026-09-09T00:12:34.362836+08:00","latest_rank":null,"duration":0},"打假网红铁头":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"六周年":{"lifecycle":"gone","first_seen":"2026-09-11T20:29:33.375400+08:00","latest_rank":null,"duration":0},"景德镇":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"汽车强国":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"代码":{"lifecycle":"gone","first_seen":"2026-09-11T14:16:24.299809+08:00","latest_rank":null,"duration":0},"美国":{"lifecycle":"declining","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"新闻":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"\"折叠屏\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"\"大模型\",":{"lifecycle":"gone","first_seen":"2026-09-11T16:53:35.498647+08:00","latest_rank":null,"duration":0},"黑洞":{"lifecycle":"gone","first_seen":"2026-09-11T14:29:56.707096+08:00","latest_rank":null,"duration":0},"签证":{"lifecycle":"stable","first_seen":"2026-09-11T14:44:28.640410+08:00","latest_rank":null,"duration":0},"女孩":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"年 月":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"工作":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"全球":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"型 新":{"lifecycle":"gone","first_seen":"2026-09-10T05:20:19.596559+08:00","latest_rank":null,"duration":0},"ChatGPT Pro":{"lifecycle":"gone","first_seen":"2026-09-11T14:29:56.707096+08:00","latest_rank":null,"duration":0},"支付宝盗刷":{"lifecycle":"gone","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"恐怖分子":{"lifecycle":"gone","first_seen":"2026-09-11T17:12:09.176349+08:00","latest_rank":null,"duration":0},"LongCat-2.0":{"lifecycle":"gone","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"孟博龙":{"lifecycle":"gone","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"搜索智能体":{"lifecycle":"gone","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"\"Apple\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"Agentic Coding":{"lifecycle":"gone","first_seen":"2026-09-11T13:07:58.333254+08:00","latest_rank":null,"duration":0},"Solidot":{"lifecycle":"gone","first_seen":"2026-09-11T21:36:39.475058+08:00","latest_rank":null,"duration":0},"\"keywords\": [":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"评论":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"阿里":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"郑钦文":{"lifecycle":"gone","first_seen":"2026-09-11T11:07:21.704427+08:00","latest_rank":null,"duration":0},"产品":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"com":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"井柏然":{"lifecycle":"gone","first_seen":"2026-09-11T14:44:28.640410+08:00","latest_rank":null,"duration":0},"企业":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"游戏":{"lifecycle":"gone","first_seen":"2026-09-09T07:42:07.468657+08:00","latest_rank":null,"duration":0},"{":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"iPhone Duo":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"积分 ":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"实习生造谣":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"鸡娃":{"lifecycle":"stable","first_seen":"2026-09-12T09:05:34.797697+08:00","latest_rank":null,"duration":0},"SIGIR":{"lifecycle":"gone","first_seen":"2026-09-11T14:16:24.299809+08:00","latest_rank":null,"duration":0},"CPI":{"lifecycle":"gone","first_seen":"2026-09-11T21:05:56.716336+08:00","latest_rank":null,"duration":0},"董建華":{"lifecycle":"gone","first_seen":"2026-09-09T21:07:09.099533+08:00","latest_rank":null,"duration":0},"香港":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"女篮世界杯":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"美联储加息":{"lifecycle":"gone","first_seen":"2026-09-11T14:29:56.707096+08:00","latest_rank":null,"duration":0},"ICML":{"lifecycle":"gone","first_seen":"2026-09-11T14:16:24.299809+08:00","latest_rank":null,"duration":0},"服贸会":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"hn":{"lifecycle":"gone","first_seen":"2026-09-09T07:33:45.507473+08:00","latest_rank":null,"duration":0},"三国":{"lifecycle":"gone","first_seen":"2026-09-11T17:12:09.176349+08:00","latest_rank":null,"duration":0},"\"油价调整\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"LPL赛制":{"lifecycle":"gone","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"推理":{"lifecycle":"gone","first_seen":"2026-09-11T14:16:24.299809+08:00","latest_rank":null,"duration":0},"iPhone 18":{"lifecycle":"gone","first_seen":"2026-09-11T11:53:56.128439+08:00","latest_rank":null,"duration":0},"是一":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"汽车":{"lifecycle":"gone","first_seen":"2026-09-11T21:05:56.716336+08:00","latest_rank":null,"duration":0},"器人":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"中方回应日公民签证费":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"刘慈欣":{"lifecycle":"gone","first_seen":"2026-09-11T21:53:21.861754+08:00","latest_rank":null,"duration":0},"摩卡港":{"lifecycle":"stable","first_seen":"2026-09-12T09:37:20.169402+08:00","latest_rank":null,"duration":0},"技术":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"支持":{"lifecycle":"gone","first_seen":"2026-09-09T00:12:34.362836+08:00","latest_rank":null,"duration":0},"摘要 ":{"lifecycle":"gone","first_seen":"2026-09-10T05:20:19.596559+08:00","latest_rank":null,"duration":0},"图谱":{"lifecycle":"gone","first_seen":"2026-09-11T14:16:24.299809+08:00","latest_rank":null,"duration":0},"包办婚姻":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"抖音":{"lifecycle":"gone","first_seen":"2026-09-11T21:53:21.861754+08:00","latest_rank":null,"duration":0},"脑梗先交钱":{"lifecycle":"gone","first_seen":"2026-09-11T16:36:25.049385+08:00","latest_rank":null,"duration":0},"\"葫芦爷爷\",":{"lifecycle":"gone","first_seen":"2026-09-11T16:53:35.498647+08:00","latest_rank":null,"duration":0},"花儿与少年":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"评测":{"lifecycle":"gone","first_seen":"2026-09-11T11:07:21.704427+08:00","latest_rank":null,"duration":0},"\"Anthropic\",":{"lifecycle":"gone","first_seen":"2026-09-11T16:53:35.498647+08:00","latest_rank":null,"duration":0},"没有":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"\"ACL\",":{"lifecycle":"gone","first_seen":"2026-09-11T12:55:02.657057+08:00","latest_rank":null,"duration":0},"\"雷宇扬\",":{"lifecycle":"gone","first_seen":"2026-09-11T16:53:35.498647+08:00","latest_rank":null,"duration":0},"机械革命笔记本":{"lifecycle":"gone","first_seen":"2026-09-11T22:07:46.278282+08:00","latest_rank":null,"duration":0},"\"评测\",":{"lifecycle":"gone","first_seen":"2026-09-11T16:53:35.498647+08:00","latest_rank":null,"duration":0},"深海矿床":{"lifecycle":"gone","first_seen":"2026-09-11T20:05:51.620896+08:00","latest_rank":null,"duration":0},"使用":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"120":{"lifecycle":"gone","first_seen":"2026-09-11T21:36:39.475058+08:00","latest_rank":null,"duration":0},"中国":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"万能公式":{"lifecycle":"gone","first_seen":"2026-09-11T20:29:33.375400+08:00","latest_rank":null,"duration":0},"代码理解":{"lifecycle":"gone","first_seen":"2026-09-11T20:05:51.620896+08:00","latest_rank":null,"duration":0},"Anthropic":{"lifecycle":"gone","first_seen":"2026-09-11T13:07:58.333254+08:00","latest_rank":null,"duration":0},"weibo":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"知识图谱":{"lifecycle":"gone","first_seen":"2026-09-11T13:07:58.333254+08:00","latest_rank":null,"duration":0},"GeoRA":{"lifecycle":"rising","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"员工":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"v1":{"lifecycle":"gone","first_seen":"2026-09-10T05:20:19.596559+08:00","latest_rank":null,"duration":0},"假捐款":{"lifecycle":"stable","first_seen":"2026-09-12T09:37:20.169402+08:00","latest_rank":null,"duration":0},"agent":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"获刑8年":{"lifecycle":"gone","first_seen":"2026-09-11T21:05:56.716336+08:00","latest_rank":null,"duration":0},"iPhone18":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"万亿参数":{"lifecycle":"gone","first_seen":"2026-09-11T18:07:37.122508+08:00","latest_rank":null,"duration":0},"985":{"lifecycle":"stable","first_seen":"2026-09-12T09:05:34.797697+08:00","latest_rank":null,"duration":0},"Tiny Website":{"lifecycle":"gone","first_seen":"2026-09-11T13:07:58.333254+08:00","latest_rank":null,"duration":0},"魔法画报":{"lifecycle":"gone","first_seen":"2026-09-11T20:29:33.375400+08:00","latest_rank":null,"duration":0},"如何":{"lifecycle":"gone","first_seen":"2026-09-08T22:28:52.211681+08:00","latest_rank":null,"duration":0},"热榜":{"lifecycle":"gone","first_seen":"2026-09-11T10:15:17.595018+08:00","latest_rank":null,"duration":0},"三体2选角":{"lifecycle":"gone","first_seen":"2026-09-11T09:53:30.730325+08:00","latest_rank":null,"duration":0},"红果短剧":{"lifecycle":"gone","first_seen":"2026-09-11T13:07:58.333254+08:00","latest_rank":null,"duration":0},"读书":{"lifecycle":"gone","first_seen":"2026-09-11T09:35:00.897537+08:00","latest_rank":null,"duration":0},"无人机":{"lifecycle":"stable","first_seen":"2026-09-12T09:37:20.169402+08:00","latest_rank":null,"duration":0},"证监会":{"lifecycle":"gone","first_seen":"2026-09-11T11:07:21.704427+08:00","latest_rank":null,"duration":0}},"topics":{"projects":{"lifecycle":"hot","latest_count":20,"peak_count":20,"duration":16},"developers":{"lifecycle":"hot","latest_count":14,"peak_count":14,"duration":10},"喷嚏图卦":{"lifecycle":"cooling","latest_count":4,"peak_count":11,"duration":9},"铂程的票圈":{"lifecycle":"cooling","latest_count":4,"peak_count":5,"duration":53},"图卦音":{"lifecycle":"cooling","latest_count":4,"peak_count":9,"duration":76},"world":{"lifecycle":"cooling","latest_count":2,"peak_count":2,"duration":3},"喷嚏意图":{"lifecycle":"cooling","latest_count":2,"peak_count":2,"duration":3},"七武士：为何赢的是农":{"lifecycle":"cooling","latest_count":2,"peak_count":2,"duration":3}}}};

  /* ── Data ── */
  var CAT_ORDER = ["wechat", "ai", "tech", "cn_tech", "dev", "news", "podcast", "youtube"];
  var ART = [];
  var now=new Date().toISOString();
  /* 全量数据按日期降序后由构建脚本切成 rss-data-0.js（首屏）与
     rss-data-1.js（后台合并）两块，页面不再内嵌数据（31MB→约0.15MB）。
     首屏严格时间排序；chunk1 合并后或刷新时应用 tier 交织。 */
  function buildArt(){
    /* 渲染前全局去重：以 源key|链接 为唯一键，防止任何合并路径（chunk/快照/远程刷新）
       造成的同源同链文章重复渲染 */
    ART=[];var _seen={};
    SOURCES.forEach(function(s){
      s.items.forEach(function(it){
        var _u=it.link||'';
        var _k=(s.key||'')+'|'+(_u&&_u!=='#'?_u:(it.title_zh||it.title||''));
        if(_seen[_k])return; _seen[_k]=1;
        ART.push({t:it.title_zh||it.title, s:it.summary_zh||it.summary||'',
          src:s.name, sk:s.key, c:s.cat, sc:s.color, ti:s.tier||3,
          /* fc 兼容两条通道：chunk 通道字段名为 full_content，远程刷新通道为 fc */
          time:it.time_str, date:it.pub_date, u:it.link||'#', fc:it.fc||it.full_content||'',
          img:it.image||it.img||'', mu:it.mu||'', mt:it.mt||'',
          bad_date:!!it.bad_date, bb:!!s.bb});
      });
    });
    var nowIso=new Date().toISOString();
    ART.forEach(function(a){ if(a.date&&a.date>nowIso) a.date=nowIso; });
    applySort();
    window.ART = ART;
  }
  /* ── Sort ── */
  var sortMode = localStorage.getItem('rss_sort_mode') || 'newest';
  /* F1 修复：'active' 按信源最近更新时间排序 */
  function applySort(){
    if(sortMode==='oldest') ART.sort(function(a,b){ return (a.date||'').localeCompare(b.date||''); });
    else if(sortMode==='active'){
      var srcLatest={};
      ART.forEach(function(a){ if(a.date){ var cur=srcLatest[a.sk]; if(!cur||a.date>cur) srcLatest[a.sk]=a.date; }});
      ART.sort(function(a,b){
        var sa=srcLatest[a.sk]||'', sb=srcLatest[b.sk]||'';
        if(sa!==sb) return sb.localeCompare(sa);
        return (b.date||'').localeCompare(a.date||'');
      });
    }
    else ART.sort(function(a,b){ return (b.date||'').localeCompare(a.date||''); });
    if(sortMode==='quality' && ANALYSIS_DATA && ANALYSIS_DATA.quality){
      var qm=ANALYSIS_DATA.quality;
      ART.sort(function(a,b){ return (qm[b.sk]||0)-(qm[a.sk]||0); });
    }
  }
  var _sortEl = document.getElementById('sortSelect');
  if(_sortEl){ _sortEl.value=sortMode; _sortEl.addEventListener('change',function(){ sortMode=this.value; localStorage.setItem('rss_sort_mode',sortMode); applySort(); wallLimit=WALL_STEP; curArt=null; renderWall(); }); }
  /* A6 修复：中文阅读速度约 400 字/分钟 */
  function estRead(a){ var mins=Math.max(1,Math.round((a.s||'').length/400)); return mins+' min'; }

  /* ── 分层交织：每 4 篇高频文章穿插 1 篇低频文章 ─ */
  function tierInterleave(){
    var hi=[], lo=[];
    ART.forEach(function(a){ (a.ti<=2 ? hi : lo).push(a); });
    var result=[], i=0, j=0;
    while(i<hi.length || j<lo.length){
      var he=Math.min(4, hi.length-i);
      for(var k=0;k<he;k++) result.push(hi[i++]);
      if(j<lo.length) result.push(lo[j++]);
    }
    ART=result;
  }

  /* ── State ── */
  var visited = {};
  try { visited = JSON.parse(localStorage.getItem('rss_read_v2')||'{}'); } catch(e){}
  var filter = {type:'all', cats:{}, src:null, unreadOnly:false, filterBm:false};
  var curArt = null;
  window.curArt = null;
  var wallLimit = 120, WALL_STEP = 80;

  /* ── Theme ── */
  var themeKey='wb_starhub_theme_v1';
  var t=localStorage.getItem(themeKey)||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
  document.documentElement.dataset.theme=t;
  var btn=document.getElementById('btnTheme');
  if(btn) btn.onclick=function(){
    var nt=document.documentElement.dataset.theme==='dark'?'light':'dark';
    try{localStorage.setItem(themeKey,nt);}catch(e){}
    document.documentElement.dataset.theme=nt;
  };

  /* ── Toolbar ── */
  function renderChips(){
    var counts={}; ART.forEach(function(a){counts[a.c]=(counts[a.c]||0)+1;});
    var h='';
    // 收藏芯片置首：手机端 chips 横向滚动时保证入口始终可见
    var bmCnt=Object.keys(_bookmarks).length;
    if(bmCnt>0) h+='<button class="chip bm-chip'+(filter.filterBm?' on':'')+'" id="bmChip" onclick="toggleBmFilter()">★ 收藏 <span class="n">'+bmCnt+'</span></button>';
    CAT_ORDER.forEach(function(c){
      if(!counts[c]) return;
      var label=CAT_LABELS[c]||c, on=filter.type==='cat'&&filter.cats[c];
      h+='<button class="chip'+(on?' on':'')+'" data-c="'+c+'">'+label+' <span class="n">'+counts[c]+'</span></button>';
    });
    document.getElementById('chips').innerHTML=h;
    document.querySelectorAll('.chip').forEach(function(el){
      if(!el.dataset.c) return; /* 无 data-c 的芯片（如收藏）保留内联 onclick，避免覆盖成 c=undefined */
      el.onclick=function(){
        var c=this.dataset.c, uo=filter.unreadOnly, bm=filter.filterBm;
        var cats=filter.type==='cat'?Object.assign({},filter.cats):{};
        if(cats[c]) delete cats[c]; else cats[c]=true;
        var keys=Object.keys(cats);
        if(keys.length===0) filter={type:'all',cats:{},unreadOnly:uo,filterBm:bm};
        else filter={type:'cat',cats:cats,src:null,unreadOnly:uo,filterBm:bm};
        curArt=null; wallLimit=WALL_STEP; renderChips(); renderWall(); renderPanel(); window.scrollTo({top:0}); updateTitle(); updateHash(); updateUnreadBtn(); updateBmChip();
      };
    });
    var pw=document.getElementById('fpillWrap');
    if(filter.type==='src'){
      var s=SRC_OBJ(filter.src);
      pw.innerHTML=s?'<button class="fpill"><span class="src-dot" style="--sc:'+s.color+'"></span>'+esc(s.name)+'<span class="x" onclick="clearSrcF(event)">✕</span></button>':'';
    } else pw.innerHTML='';
    document.getElementById('srcCnt').textContent=SOURCES.length;
    var ftN=ART.filter(function(a){return (a.s||'').length>60;}).length;
    document.getElementById('toolMeta').textContent=ART.length+' 篇 · 全文覆盖 '+ftN+'/'+ART.length;
  }
  function updateTitle(){
    var h1=document.querySelector('.toolbar h1');
    if(!h1)return;
    if(filter.type==='cat'){var labels=Object.keys(filter.cats).map(function(c){return CAT_LABELS[c]||c;});h1.textContent=labels.join(' + ');}
    else if(filter.type==='src'){var s=SRC_OBJ(filter.src);h1.textContent=s?s.name:'信源';}
    else h1.textContent='时间线';
  }
  function updateMeta(){
    var el=document.getElementById('toolMeta');if(!el)return;
    if(globalSearch){
      var list=visibleArts();
      el.textContent='命中 '+list.length+' 篇';return;
    }
    var ftN=ART.filter(function(a){return(a.s||'').length>60;}).length;
    el.textContent=ART.length+' 篇 · 全文覆盖 '+ftN+'/'+ART.length;
  }
  function SRC_OBJ(k){ return SOURCES.find(function(s){return s.key===k}); }
  window.clearSrcF=function(e){e.stopPropagation();var uo=filter.unreadOnly,bm=filter.filterBm;filter={type:'all',unreadOnly:uo,filterBm:bm};curArt=null;window.curArt=null;wallLimit=WALL_STEP;renderChips();renderWall();renderPanel();updateTitle();updateHash();updateUnreadBtn();updateBmChip();};

  /* ── Source panel ── */
  var _srcBtnEl=null;
  function toggleSrcPanel(){
    var opening=!document.body.classList.contains('src-open');
    if(opening)_srcBtnEl=document.activeElement;
    document.body.classList.toggle('src-open');
    if(opening){var si=document.getElementById('spSearch');if(si)si.focus();}
    else{if(_srcBtnEl){try{_srcBtnEl.focus();}catch(e){}_srcBtnEl=null;}}
  }
  window.toggleSrcPanel=toggleSrcPanel;
  function selectSrc(key){
    var uo=filter.unreadOnly,bm=filter.filterBm;
    if(!key){filter={type:'all',unreadOnly:uo,filterBm:bm};} else {filter={type:'src',src:key,unreadOnly:uo,filterBm:bm};}
    curArt=null; wallLimit=WALL_STEP; document.body.classList.remove('src-open');
    renderChips(); renderWall(); renderPanel(); window.scrollTo({top:0}); updateTitle(); updateHash(); updateUnreadBtn(); updateBmChip();
  }
  window.selectSrc=selectSrc;
  function renderPanel(){
    var q=(document.getElementById('spSearch').value||'').trim().toLowerCase();
    // 信源健康度总览
    var healthHtml='';
    if(ANALYSIS_DATA&&ANALYSIS_DATA.quality){
      var qm=ANALYSIS_DATA.quality,vals=Object.values(qm),n=vals.length;
      if(n>0){
        var avg=vals.reduce(function(a,b){return a+b;},0)/n;
        var good=vals.filter(function(v){return v>=70;}).length;
        var warn=vals.filter(function(v){return v>=40&&v<70;}).length;
        var bad=vals.filter(function(v){return v<40;}).length;
        healthHtml='<div class="sp-health">';
        healthHtml+='<span class="sp-health-dot good"></span>'+good+' 健康';
        healthHtml+='<span class="sp-health-dot warn"></span>'+warn+' 警告';
        healthHtml+='<span class="sp-health-dot bad"></span>'+bad+' 异常';
        healthHtml+='<span style="margin-left:auto;color:var(--faint)">均分 '+Math.round(avg)+'</span>';
        healthHtml+='</div>';
      }
    }
    var h=healthHtml+'<div class="sp-all'+(filter.type!=='src'?' on':'')+'" onclick="selectSrc(null)">☰ 全部信源<span class="n">'+ART.length+'</span></div>';
    var byCat={};
    SOURCES.forEach(function(s){
      if(!q||s.name.toLowerCase().indexOf(q)>=0){
        var cnt=s.items.length;
        if(cnt>0)(byCat[s.cat]=byCat[s.cat]||[]).push(s);
      }
    });
    Object.keys(byCat).forEach(function(c){
      byCat[c].sort(function(a,b){ return b.items.length - a.items.length; });
    });
    var any=false;
    CAT_ORDER.forEach(function(c){
      var arr=byCat[c]; if(!arr||!arr.length) return; any=true;
      var label=CAT_LABELS[c]||c;
      h+='<div class="sp-cat" data-cat="'+c+'"><span class="arrow">▼</span>'+label+'<span class="n">'+arr.length+'</span></div>';
      h+='<div class="sp-cat-body" data-body="'+c+'">';
      arr.forEach(function(s){
        var on=filter.type==='src'&&filter.src===s.key;
        h+='<div class="sp-src'+(on?' on':'')+'" data-k="'+s.key+'"><span class="src-dot" style="--sc:'+s.color+'"></span><span class="nm">'+esc(s.name)+'</span><span class="n">'+s.items.length+'</span>';
        if(ANALYSIS_DATA&&ANALYSIS_DATA.quality){var qs=ANALYSIS_DATA.quality[s.key];if(qs!=null){var qc=qs>=70?'sq-high':qs>=40?'sq-mid':'sq-low';h+='<span class="sq-badge '+qc+'">'+Math.round(qs)+'</span>';}}
        h+='</div>';
      });
      h+='</div>';
    });
    if(!any) h+='<div class="sp-none">没有匹配「'+esc(q)+'」的信源</div>';
    document.getElementById('spList').innerHTML=h;
    document.getElementById('spSearch').oninput=function(){ renderPanel(); };
    document.querySelectorAll('.sp-cat').forEach(function(el){
      el.onclick=function(){
        this.classList.toggle('folded');
        var body=document.querySelector('.sp-cat-body[data-body="'+this.dataset.cat+'"]');
        if(body) body.style.display=this.classList.contains('folded')?'none':'';
      };
    });
    document.querySelectorAll('.sp-src').forEach(function(el){
      el.onclick=function(){ selectSrc(this.dataset.k); };
    });
  }

  /* ── Card wall ── */
  var globalSearch = '';
  var _searchSrcMatch = null; // 搜索匹配到的信源 key
  var _topicBigrams = null;   // 话题标签二元组（insightSearch 设置）
  function visibleArts(){
    var q = globalSearch;
    return ART.filter(function(a){
      if(filter.type==='cat' && !filter.cats[a.c]) return false;
      if(filter.type==='src' && a.sk!==filter.src) return false;
      if(filter.filterBm && !_bookmarks[artKey(a)]) return false;
      if(filter.unreadOnly && visited[artKey(a)]) return false;
      if(q) {
        if(_searchSrcMatch) return a.sk === _searchSrcMatch;
        if(_topicBigrams&&_topicBigrams.length>=2){
          var tl=(a.t||'').toLowerCase(),hits=0;
          for(var i=0;i<_topicBigrams.length;i++){if(tl.indexOf(_topicBigrams[i])>=0)hits++;}
          return hits>=2&&hits/_topicBigrams.length>=0.15;
        }
        var ql=q.toLowerCase(); return (a.t||'').toLowerCase().indexOf(ql)>=0 || (a.s||'').toLowerCase().indexOf(ql)>=0 || (a.src||'').toLowerCase().indexOf(ql)>=0;
      }
      return true;
    });
  }
  function toggleUnread(){
    filter.unreadOnly=!filter.unreadOnly;
    wallLimit=WALL_STEP; curArt=null;
    renderWall(); renderPanel(); updateUnreadBtn();
    var em=document.getElementById('wall').querySelector('.empty-hint');
    if(filter.unreadOnly && em) em.textContent='所有文章已读';
  }
  /* U1 修复：未读计数 */
  function _countUnread(){ var n=0; ART.forEach(function(a){ if(!visited[artKey(a)]) n++; }); return n; }
  function updateUnreadBtn(){
    var b=document.getElementById('unreadToggle');
    if(!b) return;
    b.classList.toggle('on',filter.unreadOnly);
    /* A5 修复：aria-pressed */
    b.setAttribute('aria-pressed', filter.unreadOnly?'true':'false');
    /* U1 修复：显示未读计数 */
    var cnt=_countUnread();
    var cntEl=b.querySelector('.unread-cnt');
    if(!cntEl){ cntEl=document.createElement('span'); cntEl.className='unread-cnt'; cntEl.style.cssText='font-family:var(--mono);font-size:10px;opacity:.8;margin-left:2px;'; b.appendChild(cntEl); }
    cntEl.textContent=cnt>0?' '+cnt:'';
    _updateMarkAllReadBtn();
  }
  var FS_KEY='rss_reader_fontsize', FS_SIZES=['sm','md','lg'];
  function setFontSize(sz){
    var body=document.getElementById('r2Body');
    if(!body) return;
    body.classList.remove('fs-sm','fs-md','fs-lg');
    body.classList.add('fs-'+sz);
    try{localStorage.setItem(FS_KEY,sz);}catch(e){}
    var btns=document.querySelectorAll('.r2-fs-btn');
    for(var i=0;i<btns.length;i++) btns[i].classList.toggle('active',FS_SIZES[i]===sz);
  }
  function initFontSize(){
    var sz='md';
    try{var s=localStorage.getItem(FS_KEY);if(s&&FS_SIZES.indexOf(s)>=0)sz=s;}catch(e){}
    var body=document.getElementById('r2Body');
    if(body) body.classList.add('fs-'+sz);
    var btns=document.querySelectorAll('.r2-fs-btn');
    for(var i=0;i<btns.length;i++) btns[i].classList.toggle('active',FS_SIZES[i]===sz);
  }
  /* A8 修复：BM_MAX 死代码已移除 */
  var _bookmarks={}, BM_KEY='rss_bookmarks';
  function loadBookmarks(){try{_bookmarks=JSON.parse(localStorage.getItem(BM_KEY)||'{}');}catch(e){_bookmarks={};}}
  function saveBookmarks(){try{localStorage.setItem(BM_KEY,JSON.stringify(_bookmarks));}catch(e){}}
  function isBookmarked(k){return !!_bookmarks[k];}
  function toggleBookmark(a){
    var k=artKey(a);
    if(_bookmarks[k]){delete _bookmarks[k];}
    else{_bookmarks[k]={t:a.t,u:a.u,src:a.src,sk:a.sk,c:a.c,sc:a.sc,time:a.time};}
    saveBookmarks();
    var cards=document.querySelectorAll('#wall .card');
    for(var i=0;i<cards.length;i++){
      var b=cards[i].querySelector('.bm-btn');
      if(b&&cards[i].dataset.k===k) b.classList.toggle('on',!!_bookmarks[k]);
    }
    updateBmBtn();
    renderChips();
    if(filter.filterBm){wallLimit=WALL_STEP;renderWall();renderPanel();}
  }
  function toggleBmFilter(){
    filter.filterBm=!filter.filterBm;
    wallLimit=WALL_STEP; curArt=null;
    renderWall(); renderPanel(); updateBmChip();
  }
  function updateBmBtn(){
    var b=document.getElementById('r2Bm');
    if(!b||!curArt) return;
    var on=isBookmarked(artKey(curArt));
    b.classList.toggle('on',on);
    var sp=b.querySelector('span');
    if(sp) sp.textContent=on?'已收藏':'收藏';
  }
  function updateBmChip(){
    var b=document.getElementById('bmChip');
    if(b) b.classList.toggle('on',filter.filterBm);
  }
  function highlightEsc(text,q){
    var e=esc(text);if(!q)return e;
    var re=new RegExp('('+q.replace(/[.*+?^${}()|[\\]/g,'\\$&')+')','gi');
    return e.replace(re,'<mark>$1</mark>');
  }
  function artKey(a){ return a.sk+'|'+(a.u&&a.u!=='#'?a.u:a.t); }
  function renderWall(){
    var list=visibleArts(), wall=document.getElementById('wall');
    if(!list.length){
      var em=globalSearch?(_searchSrcMatch?'信源 «'+esc(SRC_OBJ(_searchSrcMatch)?SRC_OBJ(_searchSrcMatch).name:globalSearch)+'» 暂无文章':'未找到与「'+esc(globalSearch)+'」相关的文章'):(filter.filterBm?'暂无收藏文章':(filter.unreadOnly?'所有文章已读':'该筛选下没有文章'));
      /* U8 修复：空态加 CTA 按钮 */
      var cta='';
      if(globalSearch) cta='<br><button onclick="document.getElementById(&quot;globalSearchClear&quot;).click()" style="margin-top:8px;padding:6px 16px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--muted);font-size:13px;cursor:pointer;font-family:var(--body)">清除搜索</button>';
      else if(filter.type==='cat'||filter.type==='src') cta='<br><button onclick="clearSrcF(event)" style="margin-top:8px;padding:6px 16px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--muted);font-size:13px;cursor:pointer;font-family:var(--body)">查看全部文章</button>';
      else if(filter.unreadOnly) cta='<br><button onclick="toggleUnread()" style="margin-top:8px;padding:6px 16px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--muted);font-size:13px;cursor:pointer;font-family:var(--body)">显示全部文章</button>';
      wall.innerHTML='<div class="empty-hint">'+em+cta+'</div>';
      wallLimit=0;
      return;
    }
    var end=Math.min(wallLimit, list.length);
    var h='';
    if(globalSearch) {
      var bannerTxt = _searchSrcMatch ? '信源 «' + esc(SRC_OBJ(_searchSrcMatch)?SRC_OBJ(_searchSrcMatch).name:globalSearch) + '» — ' + list.length + ' 篇' : '搜索 «' + esc(globalSearch) + '» — 命中 ' + list.length + ' 篇';
      h += '<div class="search-banner">' + bannerTxt + '</div>';
    }
    for(var i=0;i<end;i++){
      var a=list[i], k=artKey(a), isVis=!!visited[k];
      var isOpen=curArt&&artKey(curArt)===k;
      var hasImg=!!a.img;
      /* 有封面图才走封面卡；无图回退纯文字紧凑卡，避免渐变占位浪费空间 */
      /* A1 修复：卡片加 tabindex 使键盘可达 */
      h+='<article class="card'+(hasImg?' cover-card':'')+(isVis?' visited':'')+(isOpen?' open':'')+'" data-k="'+esc(k)+'" tabindex="0" style="--cc:var(--cat-'+a.c+')">';
      if(hasImg){
        h+='<a class="cover" href="'+esc(a.u)+'" target="_blank" rel="noopener" tabindex="-1" aria-hidden="true" onclick="event.stopPropagation()">';
        h+='<span class="cover-fallback">'+esc((a.t||'#').charAt(0).toUpperCase())+'</span>';
        h+='<img class="cover-img" src="'+esc(a.img)+'" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">';
        h+='</a>';
      }
      h+='<div class="card-top"><span class="cat-tag" style="color:var(--cat-'+a.c+')">'+(CAT_LABELS[a.c]||a.c)+'</span>';
      h+='<span class="card-time" title="'+esc(a.date||'')+'">'+_dynTime(a)+'</span>';
      h+='<button class="bm-btn'+(isBookmarked(k)?' on':'')+'" data-k="'+esc(k)+'" title="收藏"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg></button>';
      h+='<a class="ext-btn" href="'+esc(a.u)+'" target="_blank" rel="noopener" title="原站" onclick="event.stopPropagation()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6"/><path d="M10 14 21 3"/></svg></a></div>';
      h+='<h3 class="card-title">'+highlightEsc(a.t,globalSearch)+'</h3>';
      if(a.s) h+='<p class="card-summary">'+highlightEsc(a.s,globalSearch)+'</p>';
      h+='<div class="card-foot"><span class="src-dot" style="--sc:'+a.sc+'"></span><span class="src-name">'+esc(a.src)+'</span>';
      h+='<span class="foot-meta"><button class="copy-btn" data-k="'+esc(k)+'" title="复制标题与链接"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>复制</button><button class="share-btn" data-k="'+esc(k)+'" title="分享文章"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg></button><span>'+estRead(a)+'</span></span></div>';
      h+='</article>';
    }
    wall.innerHTML=h;
    wallLimit=end;
    _scheduleWallTranslate();
  }
  /* 轻量更新：仅更新卡片已读/打开状态的 CSS 类，不重建 DOM */
  function updateCardStates(){
    var cards=document.querySelectorAll('#wall .card');
    for(var i=0;i<cards.length;i++){
      var k=cards[i].dataset.k;
      var isVis=!!visited[k];
      var isOpen=curArt&&artKey(curArt)===k;
      cards[i].classList.toggle('visited',isVis);
      cards[i].classList.toggle('open',isOpen);
    }
  }
  /* 封面图加载失败：隐藏 img 让分类色 fallback 露出（error 不冒泡，捕获阶段拦截） */
  document.getElementById('wall').addEventListener('error',function(e){
    var t=e.target;
    if(t&&t.classList&&t.classList.contains('cover-img')){ t.style.display='none'; }
  },true);
  /* A1 修复：键盘 Enter/Space 打开卡片（仅当焦点在卡片本身时，不劫持子控件） */
  document.getElementById('wall').addEventListener('keydown',function(e){
    if(e.key==='Enter'||e.key===' '){
      var card=e.target.closest('.card'); if(!card||e.target!==card)return;
      e.preventDefault(); card.click();
    }
  });
  /* 事件委托：一次性绑定，无需重新绑定 */
  document.getElementById('wall').addEventListener('click',function(e){
    var card=e.target.closest('.card'); if(!card)return;
    var k=card.dataset.k;
    var a=ART.find(function(x){return artKey(x)===k;});
    if(!a) return;
    if(e.target.closest('.ext-btn')){markRead(a);updateCardStates();return;}
    if(e.target.closest('.bm-btn')){toggleBookmark(a);return;}
    if(e.target.closest('.copy-btn')){copyArticleInfo(k);return;}
    if(e.target.closest('.share-btn')){shareArticle(a,null,e.target.closest('.share-btn'));return;}
    openReader(a);
  });
  function loadMore(){
    var list=visibleArts();
    if(wallLimit>=list.length)return;
    var old=wallLimit; wallLimit=Math.min(wallLimit+WALL_STEP,list.length);
    renderWall();
  }
  window.loadMore=loadMore;

  /* ── Reader ── */
  var _articleCache={};
  function fetchFullArticle(a){
    if(!a.u||a.u==='#') return;
    var inner=document.getElementById('r2Inner');
    if(!inner) return;
    if(a.fc&&a.fc.length>100){
      _insertFulltext(a.fc);
      return;
    }
    if(_articleCache[a.u]){
      var d=_articleCache[a.u];
      if(d.ok) _insertFulltext(d.content);
      return;
    }
    var old=inner.querySelector('.r2-ft-loading');
    if(old) old.remove();
    var ld=document.createElement('div');
    ld.className='r2-ft-loading';
    ld.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10" stroke-dasharray="30 70" stroke-linecap="round"/></svg> 正在加载全文…';
    var hint=inner.querySelector('.r2-foot-hint');
    if(hint) inner.insertBefore(ld,hint); else inner.appendChild(ld);
    var apiBase='https://starhub-refresh.vercel.app/api/article';
    fetch(apiBase+'?url='+encodeURIComponent(a.u)).then(function(r){return r.json();}).then(function(d){
      _articleCache[a.u]=d;
      var cur=inner.querySelector('.r2-ft-loading'); if(cur) cur.remove();
      if(d.ok&&d.content) _insertFulltext(d.content);
    }).catch(function(){
      var cur=inner.querySelector('.r2-ft-loading'); if(cur) cur.remove();
      /* F3 修复：全文加载失败时显示行内提示与重试按钮 */
      if(!inner.querySelector('.r2-ft-error')){
        var err=document.createElement('div');err.className='r2-ft-error';
        err.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px;animation:spin 1s linear infinite"><circle cx="12" cy="12" r="10" stroke-dasharray="30 70" stroke-linecap="round"/></svg> 全文加载失败 <button onclick="fetchFullArticle(curArt)" style="color:var(--brand-strong);background:none;border:1px solid var(--brand-line);border-radius:6px;padding:2px 10px;font-size:12px;cursor:pointer;font-family:var(--body)">重试</button>';
        var hint2=inner.querySelector('.r2-foot-hint');if(hint2)inner.insertBefore(err,hint2);else inner.appendChild(err);
      }
    });
  }
  /* ── 媒体嵌入：YouTube iframe + 播客/音频播放器 ── */
  function extractYouTubeId(url){
    if(!url) return null;
    var m=url.match(/(?:youtube\.com\/watch\?.*v=|youtu\.be\/|youtube\.com\/shorts\/)([a-zA-Z0-9_-]{6,})/);
    return m?m[1]:null;
  }
  function _renderMedia(a,container){
    if(!a||!container) return;
    var vid=extractYouTubeId(a.u);
    var hasIframe=container.querySelector('iframe[src*="youtube.com"],iframe[src*="youtu.be"]');
    if(vid&&!hasIframe){
      var ifr=document.createElement('iframe');
      ifr.src='https://www.youtube.com/embed/'+vid;
      ifr.setAttribute('loading','lazy');
      ifr.setAttribute('allowfullscreen','');
      ifr.setAttribute('allow','accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture');
      ifr.setAttribute('sandbox','allow-scripts allow-same-origin allow-popups');
      ifr.setAttribute('title','YouTube video player');
      ifr.style.cssText='width:100%;aspect-ratio:16/9;border:0;border-radius:8px;margin-bottom:12px';
      container.insertBefore(ifr,container.firstChild);
    }
    if(a.mu){
      var hasAudio=container.querySelector('audio,video');
      if(!hasAudio){
        var isAudio=a.mt&&a.mt.indexOf('audio')===0;
        var el=document.createElement(isAudio?'audio':'video');
        el.controls=true;el.preload='none';el.src=a.mu;
        el.style.cssText='width:100%;margin-bottom:12px;border-radius:8px';
        el.addEventListener('error',function(){
          el.style.display='none';
          var fb=document.createElement('div');
          fb.className='r2-media-error';
          fb.innerHTML='<p style="color:var(--muted);font-size:13px;margin:8px 0">媒体加载失败，请直接访问原始链接</p><a href="'+a.u+'" target="_blank" rel="noopener" style="color:var(--brand-strong);font-size:13px">打开原始链接 ↗</a>';
          container.insertBefore(fb,container.firstChild);
        });
        container.insertBefore(el,container.firstChild);
      }
    }
  }
  /* ── 媒体清理：关闭/切换文章时停止播放 ── */
  function _cleanupMedia(){
    var body=document.getElementById('r2Body');
    if(!body) return;
    var audios=body.querySelectorAll('audio,video');
    for(var i=0;i<audios.length;i++){try{audios[i].pause();audios[i].src='';audios[i].load();}catch(e){}}
    var iframes=body.querySelectorAll('iframe');
    for(var j=0;j<iframes.length;j++){try{iframes[j].src='about:blank';}catch(e){}}
  }
  function _insertFulltext(html){
    var inner=document.getElementById('r2Inner');
    if(!inner||inner.querySelector('.r2-fulltext')) return;
    var div=document.createElement('div');
    div.className='r2-fulltext';
    
    // Auto-format: detect if content lacks paragraph structure
    var hasParagraphs=/<p[\s>]/i.test(html);
    if(!hasParagraphs){
      // Plain text or minimal HTML - split into paragraphs
      var blocks=html.split(/\n\s*\n/);
      var formatted=blocks.map(function(block){
        block=block.trim();
        if(!block) return '';
        // Check if block contains only an image
        if(/^<img\s/i.test(block)&&block.match(/^<img\s[^>]*>$/i)){
          return block;
        }
        // Wrap text blocks in <p> tags
        return '<p>'+block.replace(/\n/g,'<br>')+'</p>';
      }).filter(function(b){return b;}).join('\n');
      div.innerHTML=formatted;
    } else {
      // Already has proper HTML structure
      div.innerHTML=html;
    }
    
    var hint=inner.querySelector('.r2-foot-hint');
    if(hint) inner.insertBefore(div,hint); else inner.appendChild(div);
    /* 正文翻译切换按钮：非中文内容时显示 */
    var ftText=div.textContent||'';
    if(ftText&&!isMostlyZh(ftText)){
      var tog=document.createElement('div');
      tog.className='r2-lang-toggle';
      tog.innerHTML='<button class="active" id="btnFtOrig">原文</button><button id="btnFtTrans">翻译</button>';
      if(hint) inner.insertBefore(tog,hint); else inner.appendChild(tog);
      document.getElementById('btnFtTrans').onclick=function(){_translateFulltext(div);};
      document.getElementById('btnFtOrig').onclick=function(){
        div.innerHTML=div._origHtml||div.innerHTML;
        var bs=tog.querySelectorAll('button');bs[0].classList.add('active');bs[1].classList.remove('active');
      };
    }
    /* 媒体嵌入：YouTube 视频 / 播客音频 */
    _renderMedia(curArt,div);
  }
  /* 正文翻译：提取文本→分块翻译→重建段落 */
  function _translateFulltext(ftDiv){
    if(!ftDiv) return;
    if(!ftDiv._origHtml) ftDiv._origHtml=ftDiv.innerHTML;
    var tog=ftDiv.nextElementSibling;
    if(tog&&tog.classList&&tog.classList.contains('r2-lang-toggle')){
      var bs=tog.querySelectorAll('button');bs[0].classList.remove('active');bs[1].classList.add('active');
    }
    ftDiv.innerHTML='<p>翻译中…</p>';
    var text=ftDiv._origText||(ftDiv._origText=(ftDiv._origHtml||ftDiv.innerHTML).replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim());
    _clientTranslate(text,function(tr){
      var cur=document.querySelector('.r2-fulltext');
      if(cur){
        var lines=tr.split(/。|！|？|\.\s+/).filter(function(s){return s.trim();});
        cur.innerHTML=lines.map(function(s){return '<p>'+esc(s.trim())+'</p>';}).join('')||'<p>'+esc(tr)+'</p>';
      }
    });
  }
  function markRead(a){visited[artKey(a)]=1;try{localStorage.setItem('rss_read_v2',JSON.stringify(visited));}catch(e){}}
  function markAllRead(){
    var list=visibleArts(),cnt=0;
    for(var i=0;i<list.length;i++){var k=artKey(list[i]);if(!visited[k]){visited[k]=1;cnt++;}}
    try{localStorage.setItem('rss_read_v2',JSON.stringify(visited));}catch(e){}
    updateCardStates();
    if(cnt>0) toast('已标记 '+cnt+' 篇为已读');
    if(filter.unreadOnly){wallLimit=WALL_STEP;renderWall();}
    renderChips(); /* U1: 刷新未读计数 */
  }
  /* F4 修复：全部已读入口——在未读模式激活时显示按钮 */
  function _updateMarkAllReadBtn(){
    var btn=document.getElementById('markAllReadBtn');
    if(!btn) return;
    btn.style.display=filter.unreadOnly?'':'none';
  }
  /* A2 修复：焦点陷阱工具函数 */
  var _prevFocusEl=null;
  function _trapFocus(container,e){
    var foc=container.querySelectorAll('button:not([disabled]),[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])');
    if(!foc.length)return;var first=foc[0],last=foc[foc.length-1];
    if(e.shiftKey){if(document.activeElement===first){e.preventDefault();last.focus();}}
    else{if(document.activeElement===last){e.preventDefault();first.focus();}}
  }
  function openReader(a){
    curArt=a; window.curArt=a; markRead(a);
    _prevFocusEl=document.activeElement;
    renderReader(); document.body.classList.add('reading');
    document.body.classList.remove('src-open');
    document.getElementById('r2Body').scrollTop=0; updateCardStates();
    var closeBtn=document.querySelector('.r2-close');if(closeBtn)closeBtn.focus();
  }
  function _navReader(dir){
    if(!curArt)return;
    var order=visibleArts();var pos=-1;
    for(var i=0;i<order.length;i++){if(artKey(order[i])===artKey(curArt)){pos=i;break;}}
    if(pos===-1)return;
    var np=pos+dir;
    if(np>=0&&np<order.length)openReader(order[np]);
  }
  window._navReader=_navReader;
  function renderReader(){
    var a=curArt; if(!a) return;
    _cleanupMedia();
    document.getElementById('r2Src').innerHTML='<span class="src-dot" style="--sc:'+a.sc+'"></span><b>'+esc(a.src)+'</b><span>·</span><span title="'+esc(a.date||'')+'">'+_dynTime(a)+'</span>';
    var openEl=document.getElementById('r2Open'); openEl.href=a.u;
    var h='<h1 class="r2-title">'+esc(a.t)+'</h1>';
    h+='<div class="r2-meta" style="--cc:var(--cat-'+a.c+')"><span class="cat">'+(CAT_LABELS[a.c]||a.c)+'</span>';
    h+='<span class="src-dot" style="--sc:'+a.sc+'"></span><span>'+esc(a.src)+'</span>';
    h+='<span>·</span><span title="'+esc(a.date||'')+'">'+_dynTime(a)+'</span><span>·</span><span>'+estRead(a)+'</span></div>';
    if(a.s){
      // Auto-format summary into paragraphs
      var formattedSummary = formatSummary(a.s);
      h+='<div class="r2-summary">'+formattedSummary+'</div>';
      if(!isMostlyZh(a.s)){
        h+='<div class="r2-lang-toggle">';
        h+='<button class="active" id="btnOrig">原文</button>';
        h+='<button id="btnTrans">翻译</button></div>';
      }
    } else {
      h+='<div class="fallback-card"><div class="fb-ico">🔗</div>';
      h+='<p>该文章暂无摘要<br>可前往原站继续阅读</p>';
      h+='<a class="fb-btn" href="'+esc(a.u)+'" target="_blank" rel="noopener">原站 ↗</a></div>';
    }
    h+='<div class="r2-foot-hint">J / K 或 ← → 切换文章 · ESC 返回</div>';
    h+='<div class="r2-actions-bottom">';
    h+='<button class="r2-nav-btn" onclick="_navReader(-1)" title="上一篇 (K)" style="display:inline-flex;align-items:center;gap:5px;padding:6px 14px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--muted);font-size:12px;font-weight:600;cursor:pointer;transition:all .15s;font-family:var(--body)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="width:13px;height:13px"><path d="M19 12H5M11 18l-6-6 6-6"/></svg> 上一篇</button>';
    h+='<button class="r2-share-btn" onclick="r2ShareClick()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg><span>分享本文</span></button>';
    h+='<button class="r2-nav-btn" onclick="_navReader(1)" title="下一篇 (J)" style="display:inline-flex;align-items:center;gap:5px;padding:6px 14px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--muted);font-size:12px;font-weight:600;cursor:pointer;transition:all .15s;font-family:var(--body)">下一篇 <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="width:13px;height:13px"><path d="M5 12h14M13 6l6 6-6 6"/></svg></button>';
    h+='</div>';
    document.getElementById('r2Inner').innerHTML=h;
    var btnT=document.getElementById('btnTrans');
    if(btnT) btnT.onclick=function(){
      var el=document.querySelector('.r2-summary');
      if(!el) return; el.innerHTML='<p>翻译中…</p>';
      _clientTranslate(a.s,function(tr){
        var cur=document.querySelector('.r2-summary');
        if(cur) cur.innerHTML=formatSummary(tr);
      });
    };
    updateBmBtn();
    fetchFullArticle(a);
  }

  // Format summary text into readable paragraphs
  function formatSummary(text){
    if(!text) return '';
    // Step 1: Normalize line endings
    var normalized = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    
    // Step 2: If no newlines exist, split by sentence-ending punctuation (Chinese + English)
    if(normalized.indexOf('\n') === -1){
      // Chinese punctuation: always split after 。！？
      normalized = normalized.replace(/([。！？])/g, '$1\n');
      
      // English punctuation: only split after .!? when followed by space+uppercase or end of string
      // Avoid splitting decimals (129.3), versions (3.7), domains (example.com), abbreviations
      normalized = normalized.replace(/(\.)(\s+[A-Z\u4e00-\u9fff])/g, '$1\n$2')  // Period before uppercase/Chinese
        .replace(/([!?])(\s+)/g, '$1\n$2');  // !? before space
    }
    
    // Step 3: Split by newlines and wrap each non-empty line in <p>
    var lines = normalized.split('\n');
    var html = lines.filter(function(line){ return line.trim().length > 0; })
      .map(function(line){ return '<p>' + esc(line.trim()) + '</p>'; })
      .join('');
    return html || '<p>' + esc(text) + '</p>';
  }
  document.getElementById('r2Body').addEventListener('scroll',function(){
    var el=this,max=el.scrollHeight-el.clientHeight;
    document.getElementById('r2Progress').style.width=(max>0?el.scrollTop/max*100:0)+'%';
  });

  /* ── Client translate ── */
  var _ctCache={},_ctPend={};
  /* 全文/摘要翻译：Agnes API 主力（服务端代理，密钥不落前端），失败块由服务端 GTX 兜底（mode:'full'），
     最终兜底原文。2026-09-08 实证修正：gtx 端点响应带 ACAO:*（浏览器可直连），当年「必遭 CORS」
     实为 GFW/网络因素误判；但全文按钮仍走服务端（质量优先 Agnes），浏览器直连仅用于批量补翻主力。 */
  function _clientTranslate(text,cb){
    if(!text||isMostlyZh(text)){cb(text);return;}
    var k=text.substring(0,100);
    if(_ctCache[k]){cb(_ctCache[k]);return;}
    if(_ctPend[k]){_ctPend[k].push(cb);return;}
    _ctPend[k]=[cb];
    /* 长文本分块翻译：每块 450 字，Agnes 每请求 ≤20 块，批间串行 */
    var chunks=[],pos=0;
    while(pos<text.length){var end=Math.min(pos+450,text.length);chunks.push(text.substring(pos,end));pos=end;}
    var _finished=0;
    function _finish(tr){ if(_finished) return; _finished=1; _ctCache[k]=tr; var p=_ctPend[k]||[]; delete _ctPend[k]; p.forEach(function(f){f(tr);}); }
    (function _agiBatch(bi){
      if(_finished) return;
      var start=bi*20,end=Math.min(start+20,chunks.length);
      if(start>=chunks.length){ _finish(chunks.join('')); return; }
      var ctrl=(typeof AbortController==='function')?new AbortController():null;
      /* 服务端 full 最坏路径（非 429 慢挂起情形）= Agnes 12s×2+400ms + GTX 6s×2+600ms ≈ 37s，
         前端 25s 超时只保证一轮 Agnes+GTX 在用户侧可见；429 快速失败路径 <10s 必然可见，
         慢路径的 GTX 兜底仍会在服务端完成并写缓存（下次点击命中） */
      var tmr=ctrl?setTimeout(function(){ctrl.abort();},25000):null;
      fetch(TR_API,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({texts:chunks.slice(start,end),mode:'full'}),signal:ctrl?ctrl.signal:undefined})
      .then(function(r){ if(tmr)clearTimeout(tmr); return r.ok?r.json():Promise.reject(new Error('http '+r.status)); })
      .then(function(j){
        if(!j||!j.ok||!j.translations||j.translations.length!==(end-start)) throw new Error('bad payload');
        for(var i=start;i<end;i++){ var t=(j.translations[i-start]||'').trim(); if(t)chunks[i]=t; }
        _agiBatch(bi+1);
      }).catch(function(){ if(tmr)clearTimeout(tmr); _agiBatch(bi+1); });
    })(0);
  }

  // ── OPML export ──
  function exportOPML(){
    var groups={};
    SOURCES.forEach(function(s){
      var cat=s.cat||'other';
      if(!groups[cat]) groups[cat]=[];
      groups[cat].push(s);
    });
    var xml='<?xml version="1.0" encoding="UTF-8"?>\n';
    xml+='<opml version="2.0">\n<head><title>StarHub RSS \u4fe1\u6e90</title><dateCreated>'+new Date().toUTCString()+'</dateCreated></head>\n<body>\n';
    CAT_ORDER.forEach(function(c){
      if(!groups[c]||!groups[c].length) return;
      var label=CAT_LABELS[c]||c;
      xml+='  <outline text="'+esc(label)+'" title="'+esc(label)+'">\n';
      groups[c].forEach(function(s){
        xml+='    <outline type="rss" text="'+esc(s.name)+'" title="'+esc(s.name)+'" xmlUrl="'+esc(s.url)+'"/>\n';
      });
      xml+='  </outline>\n';
    });
    xml+='</body>\n</opml>';
    var blob=new Blob([xml],{type:'text/xml;charset=utf-8'});
    var a=document.createElement('a');
    a.href=URL.createObjectURL(blob);
    a.download='starhub-rss-sources.opml';
    a.click();
    URL.revokeObjectURL(a.href);
    toast('已导出 '+SOURCES.length+' 个信源');
  }

  // ── Keyboard help ──
  function toggleKbdHelp(){
    var m=document.getElementById('kbdHelp');
    if(!m){m=document.createElement('div');m.id='kbdHelp';m.className='kbd-help';
    m.innerHTML='<div class="kbd-help-backdrop" onclick="toggleKbdHelp()"></div><div class="kbd-help-panel"><div class="kbd-help-hd"><h3>快捷键</h3><button class="share-close" onclick="toggleKbdHelp()">×</button></div><div class="kbd-help-body"><table><tr><td><kbd>j</kbd> / <kbd>→</kbd></td><td>下一篇文章</td></tr><tr><td><kbd>k</kbd> / <kbd>←</kbd></td><td>上一篇文章</td></tr><tr><td><kbd>/</kbd></td><td>聚焦搜索框</td></tr><tr><td><kbd>d</kbd></td><td>切换主题</td></tr><tr><td><kbd>Esc</kbd></td><td>关闭阅读器/面板</td></tr><tr><td><kbd>?</kbd></td><td>显示快捷键帮助</td></tr></table></div></div></div>';
    document.body.appendChild(m);}
    m.classList.toggle('open');
  }

  // ── Window exports ──
  window.ART = ART;
  window.closeReader = function(){ _cleanupMedia(); document.body.classList.remove('reading'); curArt=null; window.curArt=null; updateCardStates(); if(_prevFocusEl){try{_prevFocusEl.focus();}catch(e){}_prevFocusEl=null;} };
  window.closeOverlays = function(){ document.body.classList.remove('src-open'); window.closeReader(); closeInsight(); };
  window.clearSrcF = function(e){ e.stopPropagation(); var uo=filter.unreadOnly,bm=filter.filterBm; filter={type:'all',unreadOnly:uo,filterBm:bm}; curArt=null; wallLimit=WALL_STEP; renderChips(); renderWall(); renderPanel(); updateTitle(); updateHash(); updateUnreadBtn(); updateBmChip(); };
  window.toggleSrcPanel = toggleSrcPanel;
  window.selectSrc = selectSrc;
  window.toggleUnread = toggleUnread;
  window.setFontSize = setFontSize;
  window.toggleBookmark = toggleBookmark;
  window.toggleBmFilter = toggleBmFilter;
  window.markAllRead = markAllRead;
  window.exportOPML = exportOPML;
  window.toggleKbdHelp = toggleKbdHelp;

  /* ── Global search ── */
  var gsInput = document.getElementById('globalSearch');
  var gsWrap = document.getElementById('globalSearchWrap');
  var gsClear = document.getElementById('globalSearchClear');
  var _searchTimer=0;
  if(gsInput) {
    gsInput.addEventListener('input', function(){
      globalSearch = this.value.trim();
      _searchSrcMatch = null;
      _topicBigrams = null;
      if(globalSearch.length >= 1) {
        var ql = globalSearch.toLowerCase();
        var matched = SOURCES.filter(function(s){ return s.name.toLowerCase().indexOf(ql) >= 0; });
        if(matched.length === 1) _searchSrcMatch = matched[0].key;
        else if(matched.length > 1 && matched.length <= 5) {
          var exact = matched.find(function(s){ return s.name.toLowerCase() === ql; });
          if(exact) _searchSrcMatch = exact.key;
        }
      }
      gsWrap.classList.toggle('has-q', globalSearch.length > 0);
      gsWrap.classList.toggle('src-hit', !!_searchSrcMatch);
      var _sml=document.getElementById('srcMatchLabel');
      if(_sml){if(_searchSrcMatch){var _sn=SRC_OBJ(_searchSrcMatch);_sml.textContent='信源匹配：'+(_sn?_sn.name:_searchSrcMatch);_sml.style.display='';}else{_sml.style.display='none';}}
      clearTimeout(_searchTimer);
      _searchTimer=setTimeout(function(){ curArt = null; wallLimit = WALL_STEP; renderWall(); updateMeta(); },300);
    });
  }
  if(gsClear) {
    gsClear.addEventListener('click', function(){
      gsInput.value = ''; globalSearch = '';
      _searchSrcMatch = null;
      _topicBigrams = null;
      gsWrap.classList.remove('has-q', 'src-hit');
      curArt = null; wallLimit = WALL_STEP;
      renderWall(); updateMeta(); gsInput.focus();
    });
  }

  /* ── Keyboard nav ── */
  document.addEventListener('keydown', function(e){
    if(e.key==='Escape'){
      var kh=document.getElementById('kbdHelp');
      if(kh&&kh.classList.contains('open')){toggleKbdHelp();return;}
      var sm=document.getElementById('shareModal');
      if(sm&&sm.classList.contains('open')){closeShareModal();return;}
      window.closeOverlays();return;
    }
    /* A2 修复：模态对话框焦点陷阱 */
    if(e.key==='Tab'){
      var sm=document.getElementById('shareModal');
      if(sm&&sm.classList.contains('open')){_trapFocus(sm,e);return;}
      var rd=document.getElementById('reader2');
      if(document.body.classList.contains('reading')&&rd){_trapFocus(rd,e);return;}
      var sp=document.getElementById('srcPanel');
      if(document.body.classList.contains('src-open')&&sp){_trapFocus(sp,e);return;}
    }
    if(e.target.tagName==='INPUT') return;
    if(e.key==='/'){var gs=document.getElementById('globalSearch');if(gs){gs.focus();}return;}
    if(e.key==='d'&&!e.ctrlKey&&!e.metaKey&&!e.altKey){var bt=document.getElementById('btnTheme');if(bt)bt.click();return;}
    if(e.key==='?'){toggleKbdHelp();return;}
    var order=visibleArts();
    if(!curArt){if(e.key==='j'||e.key==='ArrowRight'){if(order[0])openReader(order[0]);}return;}
    var pos=-1;
    for(var i=0;i<order.length;i++){if(artKey(order[i])===artKey(curArt)){pos=i;break;}}
    if(e.key==='j'||e.key==='ArrowRight'){if(pos<order.length-1)openReader(order[pos+1]);}
    if(e.key==='k'||e.key==='ArrowLeft'){if(pos>0)openReader(order[pos-1]);}
  });

  /* ── Helpers ── */
  function esc(s){var d=document.createElement('div');d.appendChild(document.createTextNode(s||''));return d.innerHTML;}
  function adjColor(hex){
    if(document.documentElement.dataset.theme!=='dark')return hex;
    var m=/^#?([0-9a-fA-F]{6})$/.exec(hex||'');if(!m)return hex;
    var n=parseInt(m[1],16),r=(n>>16)&255,g=(n>>8)&255,b=n&255;
    var lum=(0.299*r+0.587*g+0.114*b)/255;
    if(lum>=0.35)return hex;
    r=Math.round(r+(255-r)*0.45);g=Math.round(g+(255-g)*0.45);b=Math.round(b+(255-b)*0.45);
    return '#'+((1<<24)+(r<<16)+(g<<8)+b).toString(16).slice(1);
  }
  function isMostlyZh(s){
    if(!s)return true;var c=0,n=0;
    for(var i=0;i<s.length;i++){var ch=s.charCodeAt(i);if(ch>=0x4e00&&ch<=0x9fff)c++;if(ch>32)n++;}
    return n===0||c/n>0.2;
  }

  /* ── URL hash ── */
  function updateHash(){
    var p='#view='+(filter.type==='cat'?'cat&c='+Object.keys(filter.cats).join(','):filter.type==='src'?'src&s='+encodeURIComponent(filter.src):'all');
    try{history.replaceState(null,'',p);}catch(e){}
  }
  function restoreFromHash(){
    var h=(location.hash||'').replace(/^#/,'');if(!h)return false;
    var p={};h.split('&').forEach(function(kv){var s=kv.split('=');if(s[0])p[s[0]]=decodeURIComponent(s[1]||'');});
    if(p.view==='cat'&&p.c){var cats={};p.c.split(',').forEach(function(x){if(x)cats[x]=true;});filter={type:'cat',cats:cats};return true;}
    if(p.view==='src'&&p.s){filter={type:'src',src:p.s};return true;}
    return false;
  }

  /* ── Init ── */
  var restored = restoreFromHash();
  /* 启动：chunk0 在 body 末尾同步加载（此时 DOM 已渲染，骨架可见不白屏）。
     不依赖数据的部分先行；数据到达后渲染首屏；chunk1 后台静默合并。 */
  loadBookmarks(); initFontSize(); updateHash();
  var _bootEl=document.getElementById('bootLoading');
  function _bootFinish(){ if(_bootEl&&_bootEl.parentNode)_bootEl.parentNode.removeChild(_bootEl); }
  function _bootWith(cs){
    SOURCES=cs||[];
    buildArt();
    renderChips(); renderWall(); renderPanel(); updateTitle(); updateUnreadBtn(); updateBmBtn();
    _bootFinish();
    /* 让首屏先稳定可交互，再在空闲时解析 25MB 的 chunk1，避免后台加载反过来卡住主线程 */
    var _loadRest=function(){
      loadChunk(1).then(function(){
        var n=_mergeChunk(window.__CHUNKS&&window.__CHUNKS[1]);
        if(n>0)toast('已加载全部 '+ART.length+' 篇内容（新增 '+n+' 篇）');
      }).catch(function(){});
    };
    if(window.requestIdleCallback)window.requestIdleCallback(_loadRest,{timeout:5000});
    else setTimeout(_loadRest,1200);
  }
  if(window.__CHUNKS&&window.__CHUNKS[0]){_bootWith(window.__CHUNKS[0].sources);}
  else{loadChunk(0).then(function(){_bootWith(window.__CHUNKS&&window.__CHUNKS[0]&&window.__CHUNKS[0].sources);}).catch(function(e){
    _bootFinish();
    var w=document.getElementById('wall');
    if(w)w.innerHTML='<div class="empty-hint">内容加载失败，请检查网络后刷新重试</div>';
  });}
  /* 无限滚动：接近底部自动加载更多（带节流锁） */
  var _scrollLock=false;
  window.addEventListener('scroll',function(){
    if(_scrollLock)return;
    var list=visibleArts();
    if(wallLimit>=list.length)return;
    var wrap=document.querySelector('.wall-wrap');
    if(!wrap)return;
    if(wrap.getBoundingClientRect().bottom<window.innerHeight*3){
      _scrollLock=true;
      loadMore();
      setTimeout(function(){_scrollLock=false;},150);
    }
  },{passive:true});
  /* 返回顶部按钮 */
  window.addEventListener('scroll',function(){
    var bt=document.getElementById('backTop');
    if(bt) bt.classList.toggle('show',window.scrollY>window.innerHeight*3);
  },{passive:true});
  var relEl = document.getElementById('buildRel');
  if(relEl && BUILD_TS){
    var mins=Math.max(0,Math.round((Date.now()-BUILD_TS)/60000));
    relEl.textContent=(mins<60?mins+' 分钟前':mins<1440?Math.round(mins/60)+' 小时前':Math.round(mins/1440)+' 天前');
  }

  /* ── Relative time formatter ── */
  function _fmtRelTime(dt) {
    if (!dt) return '';
    var d = new Date(dt);
    if (isNaN(d.getTime())) return dt;
    var mins = Math.max(0, Math.round((Date.now() - d.getTime()) / 60000));
    return mins < 60 ? mins + ' 分钟前' : mins < 1440 ? Math.round(mins/60) + ' 小时前' : Math.round(mins/1440) + ' 天前';
  }

  /* 旧“同域快照替换”机制已移除：chunk0+chunk1 已包含同一构建的全量数据，
     快照（约 30MB）冗余下载且与 chunk1 合并存在竞态——若快照先整体替换
     src.items、chunk1 后无去重 concat，同源同链文章会全部重复。 */

  /* ── Refresh: 后台增量更新 —— 不整页 reload，避免重新下载18MB 页面导致长时间白屏 ── */
  var _refreshing=false, _lastTotal=ART.length;
  /* ── Dynamic relative time: computed from a.date at render time, never frozen ─ */
  function _dynTime(a) {
    if (!a || !a.date) return a && a.time ? a.time : '';
    // bad_date: pub_date 不可信（构建时自动检测：wechat类目/日期倒挂/抓取时间冒充），显示绝对日期
    if (a.bad_date) {
      var d = new Date(a.date);
      if (!isNaN(d.getTime())) {
        var mo = (d.getMonth()+1).toString().padStart(2,'0');
        var da = d.getDate().toString().padStart(2,'0');
        var hh = d.getHours().toString().padStart(2,'0');
        var mm = d.getMinutes().toString().padStart(2,'0');
        return mo + '-' + da + ' ' + hh + ':' + mm;
      }
      return a.time || '';
    }
    var d = new Date(a.date);
    if (isNaN(d.getTime())) return a.time || '';
    var diff = Math.max(0, (Date.now() - d.getTime()) / 1000);
    if (diff < 60) return '刚刚';
    if (diff < 3600) return Math.floor(diff / 60) + ' 分钟前';
    if (diff < 86400) return Math.floor(diff / 3600) + ' 小时前';
    if (diff < 172800) return '昨天';
    return Math.floor(diff / 86400) + ' 天前';
  }
  function _fmtRel(dstr){
    if(!dstr) return '';
    var d=new Date(dstr); if(isNaN(d.getTime())) return '';
    var diff=(Date.now()-d.getTime())/1000; if(diff<0) diff=0;
    if(diff<60) return '刚刚';
    if(diff<3600) return Math.floor(diff/60)+' 分钟前';
    if(diff<86400) return Math.floor(diff/3600)+' 小时前';
    if(diff<172800) return '昨天';
    return Math.floor(diff/86400)+' 天前';
  }
    /* ── 数据分块加载与合并（rss-data-0/1.js）── */
  function loadChunk(i){
    return new Promise(function(resolve,reject){
      try{
        if(window.__CHUNKS&&window.__CHUNKS[i])return resolve();
        var sc=document.createElement('script'),done=false;
        var t=setTimeout(function(){if(!done){done=true;reject(new Error('chunk '+i+' timeout'));}},45000);
        sc.src='rss-data-'+i+'.js?v='+BUILD_TS;
        sc.onload=function(){if(!done){done=true;clearTimeout(t);resolve();}};
        sc.onerror=function(){if(!done){done=true;clearTimeout(t);reject(new Error('chunk '+i+' fail'));}};
        document.head.appendChild(sc);
      }catch(e){reject(e);}
    });
  }
  /* 富字段分块合并：chunk1 是构建时从 chunk0 切出的剩余项；
     按 link 去重后追加，正常路径零丢失，防御任何来源的数据重叠 */
  function _mergeChunk(pack){
    try{
      var cs=pack&&pack.sources;if(!cs||!cs.length)return 0;
      var idx={};SOURCES.forEach(function(s,i){idx[s.key]=i;});
      var added=0;
      cs.forEach(function(s){
        if(!s||!s.items||!s.items.length)return;
        var i=idx[s.key];
        var _have={};
        if(i!==undefined)SOURCES[i].items.forEach(function(_it){if(_it&&_it.link)_have[_it.link]=1;});
        /* 无 link 的 item 保留，只过滤已知重复 link，避免任何丢数据 */
        var fresh=s.items.filter(function(_it){return _it&&(!_it.link||!_have[_it.link]);});
        if(!fresh.length)return;
        if(i===undefined){s.items=fresh;SOURCES.push(s);idx[s.key]=SOURCES.length-1;added+=fresh.length;return;}
        SOURCES[i].items=SOURCES[i].items.concat(fresh);
        added+=fresh.length;
      });
      /* EV-16 修复：后台合并后仅对新增内容交织，首屏已见内容不换位 */
      if(added>0){buildArt();
        var _oldLimit=wallLimit;
        tierInterleave();
        wallLimit=Math.min(ART.length,Math.max(wallLimit,120));
        renderChips();renderWall();renderPanel();
        /* 恢复用户已滚动到的位置，避免已见内容换位 */
        if(_oldLimit>WALL_STEP) wallLimit=Math.max(wallLimit,_oldLimit);
      }
      return added;
    }catch(e){return 0;}
  }
  function _mergeRemoteSources(j){
    try{
      if(!j||!j.sources||!j.sources.length) return 0;
      var known={}; for(var i=0;i<ART.length;i++) known[artKey(ART[i])]=1;
      var added=[];
      j.sources.forEach(function(s){
        if(!s||!s.items||!s.items.length) return;
        s.items.forEach(function(it){
          if(!it||!it.u||it.u==='#') return;
          var a={t:it.t||'', s:it.s||'', src:s.name, sk:s.key, c:s.cat, sc:s.color, ti:s.tier||3,
                 time:_fmtRel(it.d), date:it.d||'', u:it.u, fc:it.fc||'', img:it.img||'', mu:it.mu||'', mt:it.mt||'', bad_date:!!it.bad_date};
          if(!a.t) return;
          var k=artKey(a);
          if(known[k]) return;
          known[k]=1; added.push(a);
        });
      });
      if(!added.length) return 0;
      added.sort(function(a,b){ return (b.date||'').localeCompare(a.date||''); });
      for(var i=added.length-1;i>=0;i--) ART.unshift(added[i]);
      ART.sort(function(a,b){ return (b.date||'').localeCompare(a.date||''); });
      tierInterleave();
      wallLimit=Math.min(ART.length, Math.max(wallLimit, WALL_STEP));
      return added.length;
    }catch(e){ return 0; }
  }
  function _applyRemote(j, manual){
    var n=_mergeRemoteSources(j);
    _lastTotal=ART.length;
    if(n>0){
      renderChips(); renderWall(); renderPanel();
      toast('已更新 '+n+' 篇新文章');
    } else if(manual){
      toast('已是最新内容');
    }
  }
  window.refreshRss=function(manual){
    if(manual===undefined) manual=true;
    if(_refreshing){ if(manual) toast('正在检查更新…'); return; }
    _refreshing=true;
    var btn=document.getElementById('refreshBtn');
    if(btn) btn.classList.add('loading');
    if(manual) toast('正在后台检查更新…');
    var settled=false;
    var ctrl=window.AbortController?new AbortController():null;
    var timer=setTimeout(function(){ if(settled) return; settled=true; if(ctrl) ctrl.abort(); _refreshing=false; if(btn) btn.classList.remove('loading'); if(manual) toast('检查超时，请稍后重试'); }, 30000);
    fetch('https://starhub-refresh.vercel.app/api/rss', ctrl?{signal:ctrl.signal}:{}).then(function(r){
      if(!r.ok) throw new Error('HTTP '+r.status);
      return r.json();
    }).then(function(j){
      if(settled) return; settled=true;
      clearTimeout(timer); _refreshing=false;
      if(btn) btn.classList.remove('loading');
      _applyRemote(j, manual);
    }).catch(function(){
      if(settled) return; settled=true;
      clearTimeout(timer); _refreshing=false;
      if(btn) btn.classList.remove('loading');
      if(manual) toast('检查更新失败，请稍后重试');
    });
  };
  /* 自动刷新：每 5 分钟用轻量 meta 接口探测新构建，仅当有新内容时才拉取合并（页面隐藏时跳过） */
  setInterval(function(){
    if(document.hidden || _refreshing) return;
    fetch('https://starhub-refresh.vercel.app/api/rss?meta=1').then(function(r){ return r.ok?r.json():null; }).then(function(m){
      if(!m || typeof m.total!=='number') return;
      if(m.total>_lastTotal) window.refreshRss(false);
    }).catch(function(){});
  }, 5*60*1000);

  /* ══════════════════════════════════════════
     Share module: Canvas card + QR code + modal
     ══════════════════════════════════════════ */
  var _qrLoaded=typeof qrcode==='function', _shareDataURL='', _toastTimer;
  function toast(msg){var t=document.getElementById('toast');if(!t)return;t.textContent=msg;t.classList.add('show');clearTimeout(_toastTimer);_toastTimer=setTimeout(function(){t.classList.remove('show');},2000);}
  function copyArticleInfo(k){
    var a=ART.find(function(x){return artKey(x)===k;});
    if(!a)return;
    var text=(a.t||'')+'\n'+(a.u&&a.u!=='#'?a.u:'');
    function done(){toast('已复制标题与链接');}
    if(navigator.clipboard&&navigator.clipboard.writeText){
      navigator.clipboard.writeText(text).then(done).catch(function(){
        try{var ta=document.createElement('textarea');ta.value=text;ta.style.cssText='position:fixed;left:-9999px';document.body.appendChild(ta);ta.select();if(document.execCommand('copy'))done();else toast('复制失败，请手动复制');document.body.removeChild(ta);}catch(e){toast('复制失败，请手动复制');}
      });
    } else {
      try{var ta2=document.createElement('textarea');ta2.value=text;ta2.style.cssText='position:fixed;left:-9999px';document.body.appendChild(ta2);ta2.select();if(document.execCommand('copy'))done();else toast('复制失败，请手动复制');document.body.removeChild(ta2);}catch(e){toast('复制失败，请手动复制');}
    }
  }

  /* QR 库已构建时内嵌（typeof qrcode==='function' 即同步可用）；
     此函数仅作为内嵌缺失时的 CDN 兜底，带 8s 超时防止 CDN 挂起 */
  function loadQRLib(){
    if(_qrLoaded) return Promise.resolve();
    return new Promise(function(resolve,reject){
      var settled=false;
      var timer=setTimeout(function(){ if(!settled){settled=true;reject(new Error('qr cdn timeout'));} },8000);
      var s=document.createElement('script');
      s.src='https://cdn.jsdelivr.net/npm/qrcode-generator@1.4.4/qrcode.min.js';
      s.onload=function(){_qrLoaded=true;settled=true;clearTimeout(timer);resolve();};
      s.onerror=function(){
        if(settled)return;
        var s2=document.createElement('script');
        s2.src='https://unpkg.com/qrcode-generator@1.4.4/qrcode.min.js';
        s2.onload=function(){_qrLoaded=true;settled=true;clearTimeout(timer);resolve();};
        s2.onerror=function(){ if(!settled){settled=true;clearTimeout(timer);reject(new Error('qr cdn failed'));} };
        document.head.appendChild(s2);
      };
      document.head.appendChild(s);
    });
  }

  function wrapText(ctx,text,maxWidth){
    var lines=[],line='';
    for(var i=0;i<text.length;i++){
      var test=line+text[i];
      if(ctx.measureText(test).width>maxWidth&&line){lines.push(line);line=text[i];}
      else{line=test;}
    }
    if(line) lines.push(line);
    return lines;
  }

  // Strip HTML tags → plain text, preserve paragraph breaks
  function stripHtmlForCanvas(html){
    if(!html) return '';
    var t = html;
    // Remove script/style
    t = t.replace(/<script[\s\S]*?<\/script>/gi, '');
    t = t.replace(/<style[\s\S]*?<\/style>/gi, '');
    // Block elements → double newline
    t = t.replace(/<\/?\s*(p|div|blockquote|pre|h[1-6]|li|tr|br)\s*[^>]*>/gi, '\n');
    // Inline images → alt text or [image]
    t = t.replace(/<img[^>]*alt\s*=\s*"([^"]*)"[^>]*>/gi, ' $1 ');
    t = t.replace(/<img[^>]*>/gi, ' [图片] ');
    // Links → keep text
    t = t.replace(/<a[^>]*>([\s\S]*?)<\/a>/gi, '$1');
    // Remaining tags
    t = t.replace(/<[^>]+>/g, '');
    // HTML entities
    t = t.replace(/&nbsp;/g, ' ').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
         .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&')
         .replace(/&#\d+;/g, '').replace(/&[a-z]+;/gi, '');
    // Collapse whitespace within lines, keep paragraph breaks
    t = t.split('\n').map(function(l){ return l.replace(/\s+/g, ' ').trim(); }).filter(function(l){ return l.length > 0; }).join('\n');
    return t.trim();
  }

  function getThemeColors(){
    var dark=document.documentElement.dataset.theme==='dark';
    return {
      bg:      dark?'#161412':'#faf9f7',
      title:   dark?'#ece7df':'#1c1917',
      summary: dark?'#a59d90':'#5f594c',
      line:    dark?'#37312a':'#ddd6c9',
      qrFg:    dark?'#ece7df':'#1c1917',
      qrBg:    dark?'#1d1a17':'#fffdf9',
      brand:   dark?'#98907f':'#857e74'
    };
  }

  function drawShareCard(a, fullText){
    var W=750, PAD=40, GAP_T=28, GAP_S=16, GAP_M=24;
    var c=document.createElement('canvas');
    var ctx=c.getContext('2d');
    var col=getThemeColors();
    var font=getComputedStyle(document.body).fontFamily;
    var catColor=a.sc||'#2f5d8a';
    if(document.documentElement.dataset.theme==='dark') catColor=adjColor(a.sc||'#8fb3d9');

    // ─ Resolve content: full text preferred, fallback to summary ──
    var BODY_FONT = 14;
    var BODY_LH = 1.7;
    var MAX_CONTENT_CHARS = 3000;
    var MAX_LINES = 78; /* 限制画布高度，超出移动端 canvas 尺寸上限会导致绘制空白 */
    var contentText = '';
    var useFull = false;
    if(fullText && fullText.length > 60){
      useFull = true;
      contentText = fullText;
      if(contentText.length > MAX_CONTENT_CHARS){
        contentText = contentText.slice(0, MAX_CONTENT_CHARS);
        var lastNl = contentText.lastIndexOf('\n');
        if(lastNl > MAX_CONTENT_CHARS * 0.7) contentText = contentText.slice(0, lastNl);
        contentText += '\n\n…… 全文请扫描二维码阅读';
      }
    }

    // ── Measure pass ──
    ctx.font='26px '+font;
    var titleLines=wrapText(ctx, a.t||'无标题文章', W-PAD*2);
    var titleH=titleLines.length*(26*1.45);
    var contentLines=[];
    var contentH=0;
    if(useFull){
      ctx.font=BODY_FONT+'px '+font;
      var paras = contentText.split('\n');
      for(var pi=0;pi<paras.length;pi++){
        var pLines = wrapText(ctx, paras[pi], W-PAD*2);
        for(var li=0;li<pLines.length;li++) contentLines.push(pLines[li]);
        if(pi<paras.length-1) contentLines.push(''); // blank line between paragraphs
      }
      if(contentLines.length > MAX_LINES){
        contentLines = contentLines.slice(0, MAX_LINES);
        contentLines.push('');
        contentLines.push('…… 全文请扫描二维码阅读');
      }
      contentH = contentLines.length * (BODY_FONT * BODY_LH);
    } else {
      ctx.font='15px '+font;
      if(a.s) contentLines=wrapText(ctx, a.s, W-PAD*2);
      contentH = contentLines.length*(15*1.7);
    }
    var H=PAD+50+GAP_T+titleH+GAP_S+contentH+(contentH>0?GAP_M:0)+1+GAP_M+110+36;

    // ── Create canvas at 2x ──
    c.width=W*2; c.height=H*2;
    ctx.scale(2,2);

    // ── Background with rounded corners ──
    var R=16;
    ctx.beginPath();
    ctx.moveTo(R,0);ctx.lineTo(W-R,0);ctx.quadraticCurveTo(W,0,W,R);
    ctx.lineTo(W,H-R);ctx.quadraticCurveTo(W,H,W-R,H);
    ctx.lineTo(R,H);ctx.quadraticCurveTo(0,H,0,H-R);
    ctx.lineTo(0,R);ctx.quadraticCurveTo(0,0,R,0);
    ctx.closePath();ctx.fillStyle=col.bg;ctx.fill();

    var y=PAD;
    // ── Top bar ──
    ctx.fillStyle=catColor;
    ctx.beginPath();ctx.arc(PAD+3.5,y+6,3.5,0,Math.PI*2);ctx.fill();
    ctx.font='bold 12px '+font;
    ctx.fillStyle=catColor;
    ctx.fillText((CAT_LABELS[a.c]||a.c).toUpperCase(),PAD+14,y+10);
    ctx.font='12px '+font;
    ctx.fillStyle=col.brand;
    ctx.textAlign='right';
    ctx.fillText('StarHub RSS 聚合',W-PAD,y+10);
    ctx.textAlign='left';
    y+=50+GAP_T;

    // ── Title (never truncated) ──
    ctx.font='bold 26px '+font;
    ctx.fillStyle=col.title;
    for(var i=0;i<titleLines.length;i++){
      ctx.fillText(titleLines[i],PAD,y);
      y+=26*1.45;
    }
    y+=GAP_S;

    // ── Content: full text or summary ──
    if(contentLines.length){
      if(useFull){
        ctx.font=BODY_FONT+'px '+font;
        ctx.fillStyle=col.summary;
        for(var i=0;i<contentLines.length;i++){
          if(contentLines[i]==='') { y+=BODY_FONT*BODY_LH*0.6; continue; }
          ctx.fillText(contentLines[i],PAD,y);
          y+=BODY_FONT*BODY_LH;
        }
      } else {
        ctx.font='15px '+font;
        ctx.fillStyle=col.summary;
        for(var i=0;i<contentLines.length;i++){
          ctx.fillText(contentLines[i],PAD,y);
          y+=15*1.7;
        }
      }
      y+=GAP_M;
    }

    // ── Separator ──
    ctx.strokeStyle=col.line;ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(PAD,y);ctx.lineTo(W-PAD,y);ctx.stroke();
    y+=GAP_M;

    // ── Bottom: source + QR ─
    ctx.fillStyle=a.sc||'#2f5d8a';
    ctx.beginPath();ctx.arc(PAD+4,y+6,4,0,Math.PI*2);ctx.fill();
    ctx.font='bold 12px '+font;
    ctx.fillStyle=col.title;
    var srcTxt=a.src||'';
    ctx.fillText(srcTxt,PAD+16,y+10);
    ctx.font='12px '+font;
    ctx.fillStyle=col.summary;
    ctx.fillText('· '+_dynTime(a),PAD+16+ctx.measureText(srcTxt).width+6,y+10);

    ctx.font='11px '+font;
    ctx.fillStyle=col.brand;
    ctx.fillText('长按识别 · 阅读原文',PAD,y+40);

    var qrSize=90, qrX=W-PAD-qrSize, qrY=y;
    if(typeof qrcode==='function'){
      try{
        var qrUrl=(a.u&&a.u!=='#')?a.u:location.href;
        var qr=qrcode(0,'M');
        qr.addData(qrUrl);qr.make();
        var cnt=qr.getModuleCount();
        var cell=qrSize/cnt;
        ctx.fillStyle=col.qrBg;
        ctx.fillRect(qrX-4,qrY-4,qrSize+8,qrSize+8);
        ctx.fillStyle=col.qrFg;
        for(var r=0;r<cnt;r++)for(var c2=0;c2<cnt;c2++){
          if(qr.isDark(r,c2)) ctx.fillRect(qrX+c2*cell,qrY+r*cell,Math.ceil(cell),Math.ceil(cell));
        }
      }catch(e){
        ctx.fillStyle=col.summary;ctx.font='11px '+font;
        ctx.textAlign='center';ctx.fillText('二维码暂不可用',qrX+qrSize/2,qrY+qrSize/2);
        ctx.textAlign='left';
      }
    } else {
      ctx.fillStyle=col.summary;ctx.font='11px '+font;
      ctx.textAlign='center';ctx.fillText('二维码暂不可用',qrX+qrSize/2,qrY+qrSize/2);
      ctx.textAlign='left';
    }

    return c.toDataURL('image/png');
  }

  function shareArticle(a,platform,btn){
    if(!a) return;
    if(btn) btn.classList.add('loading');
    // Gather full text from available sources
    var fullText = '';
    var ftEl = document.querySelector('.r2-fulltext');
    if(ftEl && !a._af) fullText = stripHtmlForCanvas(ftEl.innerText || ftEl.textContent);
    if(!fullText && a.fc && a.fc.length > 100) fullText = stripHtmlForCanvas(a.fc);
    if(!fullText && _articleCache[a.u] && _articleCache[a.u].ok) fullText = stripHtmlForCanvas(_articleCache[a.u].content);

    function doShare(text){
      /* 内嵌 QR 后同步出图：模态框立即弹出，不再等待任何网络请求 */
      var url='';
      try{ url = drawShareCard(a, text); }catch(e){}
      if(btn) btn.classList.remove('loading');
      if(!url){
        /* Canvas 不可用（getContext null / toDataURL 异常）：降级纯文本信息卡 */
        toast('图片生成失败，已转为文字分享');
        showShareTextCard(a, text);
        return;
      }
      _shareDataURL = url;
      showShareModal(url);
      if(!_qrLoaded) loadQRLib().catch(function(){});
    }

    if(fullText){ doShare(fullText); return; }

    // Fetch full text from API — 3s 超时：vercel 域名国内移动端常不可达，快速降级为摘要分享
    if(a.u && a.u !== '#'){
      var apiBase = 'https://starhub-refresh.vercel.app/api/article';
      var settled=false;
      function once(text){ if(settled)return; settled=true; doShare(text); }
      var ctrl = (typeof AbortController==='function') ? new AbortController() : null;
      var timer = ctrl ? setTimeout(function(){ once(''); }, 3000) : null;
      fetch(apiBase + '?url=' + encodeURIComponent(a.u), ctrl?{signal:ctrl.signal}:{}).then(function(r){ return r.json(); }).then(function(d){
        if(timer) clearTimeout(timer);
        var text='';
        if(d.ok && d.content){
          text = stripHtmlForCanvas(d.content);
          if(_articleCache) _articleCache[a.u] = d;
        }
        once(text);
      }).catch(function(){ if(timer) clearTimeout(timer); once(''); });
    } else {
      doShare('');
    }
  }

  function showShareModal(url){
    var m=document.getElementById('shareModal');
    var img=document.getElementById('shareImg');
    img.src=url; img.style.display='';
    var tc=document.getElementById('shareTextCard');
    if(tc) tc.style.display='none';
    var bs=document.getElementById('btnShareSave'); if(bs) bs.style.display='';
    var bc=document.getElementById('btnShareCopy'); if(bc) bc.style.display='';
    var ct=document.getElementById('btnShareCopyText'); if(ct) ct.style.display='none';
    m.classList.add('open');
    var closeBtn=m.querySelector('.share-close');
    if(closeBtn) closeBtn.focus();
  }

  /* ── Canvas 不可用时的纯文本降级卡 ── */
  function _shareTextCard(a, text){
    var lines=[];
    lines.push('【'+(CAT_LABELS[a.c]||a.c||'')+'】'+(a.t||'无标题文章'));
    lines.push('');
    if(text&&text.length>60){ lines.push(text.slice(0,1500)); lines.push(''); }
    else if(a.s){ lines.push(a.s); lines.push(''); }
    lines.push('来源：'+(a.src||'')+(a.time?(' · '+a.time):''));
    lines.push('原文：'+((a.u&&a.u!=='#')?a.u:location.href));
    lines.push('—— StarHub RSS 聚合');
    return lines.join('\n');
  }

  function showShareTextCard(a, text){
    _shareDataURL='';
    var img=document.getElementById('shareImg');
    if(img) img.style.display='none';
    var tc=document.getElementById('shareTextCard');
    if(tc){ tc.textContent=_shareTextCard(a,text); tc.style.display='block'; }
    var bs=document.getElementById('btnShareSave'); if(bs) bs.style.display='none';
    var bc=document.getElementById('btnShareCopy'); if(bc) bc.style.display='none';
    var ct=document.getElementById('btnShareCopyText'); if(ct) ct.style.display='';
    document.getElementById('shareModal').classList.add('open');
  }

  function copyShareText(){
    var tc=document.getElementById('shareTextCard');
    if(!tc||!tc.textContent) return;
    if(navigator.clipboard&&navigator.clipboard.writeText){
      navigator.clipboard.writeText(tc.textContent).then(function(){toast('文字已复制');}).catch(function(){toast('复制失败');});
    } else { toast('当前浏览器不支持复制'); }
  }

  function closeShareModal(){
    document.getElementById('shareModal').classList.remove('open');
    if(_prevFocusEl){try{_prevFocusEl.focus();}catch(e){}_prevFocusEl=null;}
  }

  function saveShareImage(){
    if(!_shareDataURL) return;
    var a=document.createElement('a');
    a.href=_shareDataURL;a.download='starhub-share.png';
    document.body.appendChild(a);a.click();document.body.removeChild(a);
    toast('图片已下载');
  }

  function copyShareImage(){
    if(!_shareDataURL) return;
    fetch(_shareDataURL).then(function(r){return r.blob();}).then(function(blob){
      if(navigator.clipboard&&window.ClipboardItem){
        navigator.clipboard.write([new ClipboardItem({'image/png':blob})]).then(function(){
          toast('图片已复制到剪贴板');
        }).catch(function(){toast('复制失败，请长按图片手动保存');});
      } else {toast('当前浏览器不支持复制图片');}
    }).catch(function(){toast('复制失败');});
  }

  function copyFullHtml(){
    var a = curArt;
    if(!a){ toast('请先打开文章'); return; }
    var ftEl = document.querySelector('.r2-fulltext');
    var contentHtml = '';
    if(ftEl){ contentHtml = ftEl.innerHTML; }
    else if(a.fc && a.fc.length > 100){ contentHtml = a.fc; }
    else if(_articleCache[a.u] && _articleCache[a.u].ok){ contentHtml = _articleCache[a.u].content; }
    var srcName = esc(a.src||'');
    var catLabel = CAT_LABELS[a.c]||a.c;
    var fullHtml = '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
      + '<meta name="viewport" content="width=device-width,initial-scale=1">'
      + '<title>' + esc(a.t) + ' · StarHub</title>'
      + '<style>'
      + 'body{max-width:720px;margin:40px auto;padding:0 20px;font-family:-apple-system,BlinkMacSystemFont,"Noto Sans SC",sans-serif;line-height:1.8;color:#1c1917;background:#fafaf9;}'
      + '.meta{display:flex;align-items:center;gap:8px;font-size:13px;color:#78716c;margin-bottom:24px;flex-wrap:wrap;}'
      + '.meta .cat{color:#2563eb;font-weight:600;}'
      + '.meta .dot{width:8px;height:8px;border-radius:50%;display:inline-block;background:' + (a.sc||'#78716c') + ';}'
      + 'h1{font-size:28px;font-weight:900;line-height:1.3;margin:0 0 16px;}'
      + 'img{max-width:100%;height:auto;border-radius:8px;margin:16px 0;}'
      + 'p{margin:0 0 16px;}a{color:#2563eb;}blockquote{border-left:3px solid #d6d3d1;padding-left:16px;color:#57534e;margin:16px 0;}'
      + 'pre{background:#f5f5f4;padding:16px;border-radius:8px;overflow-x:auto;font-size:13px;}'
      + 'code{background:#f5f5f4;padding:2px 6px;border-radius:4px;font-size:13px;}'
      + '.footer{margin-top:40px;padding-top:20px;border-top:1px solid #e7e5e4;font-size:12px;color:#a8a29e;}'
      + '.footer a{color:#78716c;text-decoration:none;}'
      + '</style></head><body>'
      + '<h1>' + esc(a.t) + '</h1>'
      + '<div class="meta"><span class="cat">' + catLabel + '</span>'
      + '<span class="dot"></span><span>' + srcName + '</span>'
      + '<span>·</span><span title="' + esc(a.date||'') + '">' + _dynTime(a) + '</span></div>';
    if(contentHtml){ fullHtml += '<div class="content">' + contentHtml + '</div>'; }
    else if(a.s){ fullHtml += '<div class="content"><p>' + esc(a.s) + '</p></div>'; }
    fullHtml += '<div class="footer">来源：<a href="' + esc(a.u) + '" target="_blank">' + srcName + ' ↗</a> · StarHub RSS 聚合</div>'
      + '</body></html>';
    if(navigator.clipboard && navigator.clipboard.writeText){
      navigator.clipboard.writeText(fullHtml).then(function(){
        toast('全文 HTML 已复制到剪贴板');
      }).catch(function(){ _fallbackCopy(fullHtml); });
    } else { _fallbackCopy(fullHtml); }
  }
  function _fallbackCopy(text){
    var ta = document.createElement('textarea');
    ta.value = text; ta.style.cssText = 'position:fixed;left:-9999px';
    document.body.appendChild(ta); ta.select();
    try{ document.execCommand('copy'); toast('全文 HTML 已复制'); }
    catch(e){ toast('复制失败，请手动复制'); }
    document.body.removeChild(ta);
  }

  window.shareArticle=shareArticle;
  window.r2ShareClick=function(){ shareArticle(curArt,null,document.querySelector('.r2-share-btn')); };
  window.closeShareModal=closeShareModal;
  window.saveShareImage=saveShareImage;
  window.copyShareImage=copyShareImage;
  window.copyFullHtml=copyFullHtml;
  window.toast=toast;

  /* ══════ AI 动态流面板（AIHOT + AGI Hunt） ══════ */
  var AIHOT_API = 'https://aihot.virxact.com/api/v1/items?mode=all&window=24h&limit=40';
  var AGIHUNT_API = 'https://starhub-refresh.vercel.app/api/agihunt';
  var AIHOT_CATS = {'ai-models':['AI 模型','#2563eb'],'ai-products':['AI 产品','#7c3aed'],industry:['行业动态','#0891b2'],paper:['论文','#d97706'],tip:['技巧观点','#dc2626']};
  var afLoaded = false;
  var afItems = [], afCursor = '', afFilter = 'all';
  var afAgiSort = 'hot';  // hot | new
  var afRefreshing = false;
  var AGIHUNT_CHANNELS = [
    ['models','模型','#2563eb'],['research','研究','#7c3aed'],['coding-agents','编程&Agent','#059669'],
    ['products','应用','#b45309'],['multimodal','多模态','#db2777'],['infra','Infra','#475569'],
    ['hardware','具身','#0891b2'],['funding','创投','#a16207'],['policy','安全','#dc2626'],
    ['agi','漫话AGI','#c026d3'],['companies','公司和人','#4d7c0f'],['fun','Fun','#ea580c']
  ];

  function _escH(s){ return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
  function _normT(s){ return (s||'').toLowerCase().replace(/[^\p{L}\p{N}]+/gu,''); }
  // 检测标题是否主要为非中文（需要翻译）
  function _needsTranslation(t){ if(!t) return false; var cjk=(t.match(/[一-鿿㐀-䶿]/g)||[]).length; return cjk < t.replace(/[\s\d\p{P}]/gu,'').length * 0.3; }
  // 批量翻译 AI 动态流英文标题：主力 = 浏览器端 GTX 直连（用户本地 IP，端点响应带 ACAO:* 实证开放；
  // 服务端共享 DC 出口反而会被 Google 频率限流——线上实测 gtx 429）；失败条目再走服务端 API 兜底
  // （api/translate mode:'bulk'：GTX 尽力 → Agnes 限量）。引擎分流策略（用户定版）：Agnes 仅留
  // 给全文/摘要按钮（mode:'full'）与兜底，绝不作为批量主力。
  var TR_API = 'https://starhub-refresh.vercel.app/api/translate';
  /* 浏览器端 GTX 批量直译：并发 3，返回与 texts 等长的译文数组（失败为 ''，由调用方决定服务端兜底） */
  function _browserGtx(texts){
    var out=[],i=0,done=0;
    for(var k=0;k<texts.length;k++) out.push('');
    return new Promise(function(resolve){
      if(!texts.length){ resolve(out); return; }
      function one(){
        if(i>=texts.length) return;
        var idx=i++;
        var ctrl=(typeof AbortController==='function')?new AbortController():null;
        var tmr=ctrl?setTimeout(function(){ctrl.abort();},8000):null;
        fetch('https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=zh-CN&dt=t&q='+encodeURIComponent(String(texts[idx]).slice(0,500)),{signal:ctrl?ctrl.signal:undefined})
        .then(function(r){ if(tmr)clearTimeout(tmr); return r.ok?r.json():Promise.reject(new Error('gtx '+r.status)); })
        .then(function(j){
          var tr=((j[0]||[]).map(function(x){ return (x&&x[0])||''; }).join('')||'').trim();
          if(tr) out[idx]=tr;
        }).catch(function(){ if(tmr)clearTimeout(tmr); })
        .then(function(){ done++; if(done>=texts.length){ resolve(out); } else { one(); } });
      }
      for(var w=0;w<Math.min(3,texts.length);w++) one();
    });
  }
  function _translateAfItems(){
    var toTranslate = afItems.filter(function(it){ return !it._zh && _needsTranslation(it.title); });
    if(!toTranslate.length) return;
    // 每批 15 条（与服务端兜底上限匹配），最多 8 批（120 条，覆盖 AIHOT+AGI 全量）
    var batches = []; for(var i=0;i<toTranslate.length && batches.length<8;i+=15) batches.push(toTranslate.slice(i,i+15));
    var applied = 0;
    function _apply(trs, batch){
      batch.forEach(function(it, idx){
        var zh = (trs[idx]||'').trim();
        if(zh && !it._zh){ it._zh = zh; applied++; }
      });
    }
    /* 服务端兜底：仅浏览器端 GTX 失败的零星条目（TR_API bulk：GTX 尽力 → Agnes 限量） */
    function _serverFallback(texts){
      return new Promise(function(resolve){
        var ctrl = (typeof AbortController === 'function') ? new AbortController() : null;
        var tmr = ctrl ? setTimeout(function(){ ctrl.abort(); }, 12000) : null;
        fetch(TR_API, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ texts: texts, mode: 'bulk' }),
          signal: ctrl ? ctrl.signal : undefined
        }).then(function(r){
          if(tmr) clearTimeout(tmr);
          return r.ok ? r.json() : Promise.reject(new Error('http ' + r.status));
        }).then(function(j){
          if(!j || !j.ok || !j.translations || j.translations.length !== texts.length) throw new Error('bad payload');
          resolve(j.translations);
        }).catch(function(){
          if(tmr) clearTimeout(tmr);
          resolve(null);
        });
      });
    }
    // 逐批推进：浏览器直连主力，批间 300ms 温和节奏（服务端仅承接零星失败）
    (async function(){
      for(var b=0;b<batches.length;b++){
        var batch = batches[b];
        var trs = await _browserGtx(batch.map(function(it){ return it.title; }));
        _apply(trs, batch);
        var failed = [];
        trs.forEach(function(z, idx){ if(!z) failed.push(idx); });
        if(failed.length){
          var fb = await _serverFallback(failed.map(function(k){ return batch[k].title; }));
          if(fb) failed.forEach(function(k, fi){ var zh=(fb[fi]||'').trim(); if(zh && !batch[k]._zh){ batch[k]._zh = zh; applied++; } });
        }
        if(b+1<batches.length) await new Promise(function(rs){ setTimeout(rs,300); });
      }
      if(applied) _renderAll();
    })();
  }
  /* ── RSS 卡片墙运行时翻译兜底：构建期翻译熔断/漏网的英文条目，挂载于 renderWall 末尾；
     主力 = 浏览器端 GTX 直连，失败条目走服务端 API 兜底；_zhTried 标记防重复请求，
     完成后重渲染刷新卡片（终止条件：cands 耗尽）。 */
  var _wallTrBusy=0,_wallDirty=0;
  function _scheduleWallTranslate(){ setTimeout(_translateWallItems,120); }
  function _translateWallItems(){
    if(_wallTrBusy) return;
    var cands=ART.filter(function(a){ return !a._zhTried && (_needsTranslation(a.t)||(a.s&&_needsTranslation(a.s))); });
    if(!cands.length) return;
    var batch=cands.slice(0,10);
    batch.forEach(function(a){ a._zhTried=1; });
    _wallTrBusy=1;
    var texts=[],map=[];
    batch.forEach(function(a){
      if(_needsTranslation(a.t)){ texts.push(a.t); map.push({a:a,f:'t'}); }
      if(a.s&&_needsTranslation(a.s)){ texts.push(a.s); map.push({a:a,f:'s'}); }
    });
    if(!texts.length){ _wallTrBusy=0; return; }
    (async function(){
      var trs = await _browserGtx(texts);
      var failed=[];
      trs.forEach(function(zhRaw,idx){
        var m=map[idx]; if(!m) return;
        var zh=(zhRaw||'').trim(); if(!zh){ failed.push(idx); return; }
        if(m.f==='t'&&_needsTranslation(m.a.t)) m.a.t=zh;
        else if(m.f==='s'&&m.a.s&&_needsTranslation(m.a.s)) m.a.s=zh;
      });
      if(failed.length){
        var fbTexts=failed.map(function(k){ return texts[k]; });
        var ctrl=(typeof AbortController==='function')?new AbortController():null;
        var tmr=ctrl?setTimeout(function(){ctrl.abort();},12000):null;
        try{
          var resp=await fetch(TR_API,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({texts:fbTexts,mode:'bulk'}),signal:ctrl?ctrl.signal:undefined});
          if(tmr)clearTimeout(tmr);
          var j=(resp&&resp.ok)?(await resp.json().catch(function(){ return null; })):null;
          if(j&&j.ok&&j.translations&&j.translations.length===fbTexts.length){
            fbTexts.forEach(function(_,fi){
              var m=map[failed[fi]]; if(!m) return;
              var zh=(j.translations[fi]||'').trim(); if(!zh) return;
              if(m.f==='t'&&_needsTranslation(m.a.t)) m.a.t=zh;
              else if(m.f==='s'&&m.a.s&&_needsTranslation(m.a.s)) m.a.s=zh;
            });
          }
        }catch(e){ if(tmr)clearTimeout(tmr); }
      }
      _wallDirty=1;
      _wallTrBusy=0;
      if(_wallDirty){ _wallDirty=0; renderWall(); }
      // 批间节流：温和节奏防单 IP 突发高频（失败条目保留原文，下批继续）
      setTimeout(_translateWallItems,2500);
    })();
  }
  function _fmtRel(s){ if(!s) return ''; try{ var d=new Date(s),n=Date.now(),diff=n-d.getTime(); if(diff<0)return ''; var m=Math.floor(diff/60000); if(m<1)return '刚刚'; if(m<60)return m+' 分钟前'; var h=Math.floor(m/60); if(h<24)return h+' 小时前'; return Math.floor(h/24)+' 天前'; }catch(e){return '';} }

  function toggleAiFeed(){
    var open = document.body.classList.toggle('ai-open');
    document.getElementById('btnAiFeed').classList.toggle('on', open);
    var hb=document.getElementById('btnHot'); if(hb) hb.classList.toggle('on', open && afTab==='hot');
    if(open && !afLoaded) _loadAll();
  }
  window.toggleAiFeed = toggleAiFeed;

  /* ── 刷新（参照主页 refreshRss 模式） ── */
  function refreshAiFeed(){
    /* D6: 热榜 Tab 下刷新热榜数据 */
    if(afTab==='hot'){
      _hotLoaded=false; _hotLoading=false;
      loadHotSnapshot();
      return;
    }
    if(afRefreshing) return;
    if(!afLoaded) { _loadAll(); return; }
    afRefreshing = true;
    var btn = document.getElementById('afRefreshBtn');
    if(btn) btn.classList.add('loading');
    var settled = false;
    var timer = setTimeout(function(){
      if(settled) return; settled = true; afRefreshing = false;
      if(btn) btn.classList.remove('loading');
    }, 30000);
    _loadAll(true).then(function(){
      if(settled) return; settled = true; afRefreshing = false;
      clearTimeout(timer);
      if(btn) btn.classList.remove('loading');
    }).catch(function(){
      if(settled) return; settled = true; afRefreshing = false;
      clearTimeout(timer);
      if(btn) btn.classList.remove('loading');
    });
  }
  window.refreshAiFeed = refreshAiFeed;



  /* ── 统一加载 AIHOT + AGI Hunt（渐进式渲染：先到先渲染，全部加超时兜底） ── */
  async function _loadAll(isRefresh){
    var list = document.getElementById('afList');
    var upd = document.getElementById('afUpdated');
    if(!isRefresh){
      list.innerHTML = '<div class="af-loading"><span class="af-spin"></span> 加载中…</div>';
      upd.textContent = '加载中…';
    }
    var seen = new Set();
    var merged = [];
    var rendered = false;

    // ① AIHOT 请求：超时 10s（移动端弱网兆底）
    var aiCtrl = (typeof AbortController === 'function') ? new AbortController() : null;
    var aiTimer = aiCtrl ? setTimeout(function(){ aiCtrl.abort(); }, 10000) : null;
    var aihotP = fetch(AIHOT_API, aiCtrl ? { signal: aiCtrl.signal } : {}).then(function(r){
      if(!r.ok) throw new Error('http '+r.status);
      return r.json();
    }).then(function(j){
      if(aiTimer) clearTimeout(aiTimer);
      afCursor = (j.page&&j.page.hasMore) ? (j.page.nextCursor||'') : '';
      (j.items||[]).forEach(function(it){
        var k=_normT(it.title);
        if(!seen.has(k)){seen.add(k); merged.push(Object.assign({},it,{_src:'aihot'}));}
      });
      // AIHOT 先到先渲染，不等 AGI Hunt
      if(!rendered && merged.length){
        rendered = true;
        afItems = merged.slice();
        afItems.sort(function(a,b){return (b.publishedAt||b.published_at||'').localeCompare(a.publishedAt||a.published_at||'');});
        _renderAll();
        _translateAfItems();
        upd.textContent = 'AI 动态流 · ' + afItems.length + ' 条 · 更新于 ' + new Date().toLocaleTimeString('zh-CN',{hour12:false});
      }
    }).catch(function(){ if(aiTimer) clearTimeout(aiTimer); afCursor=''; });

    // ② AGI Hunt 请求（顺序请求，避免移动端并发连接槽排队）：单请求 5s 超时 + 总超时 30s
    var agiCtrl = (typeof AbortController === 'function') ? new AbortController() : null;
    var agiTimer = agiCtrl ? setTimeout(function(){ agiCtrl.abort(); }, 30000) : null;
    var today = new Date(Date.now()+8*3600000).toISOString().slice(0,10);
    var agihuntP = (async function(){
      for(var ci=0; ci<AGIHUNT_CHANNELS.length; ci++){
        if(agiCtrl && agiCtrl.signal.aborted) break;
        var ch = AGIHUNT_CHANNELS[ci];
        var chCtrl = (typeof AbortController === 'function') ? new AbortController() : null;
        var chTimer = chCtrl ? setTimeout(function(){ chCtrl.abort(); }, 5000) : null;
        try{
          var r = await fetch(AGIHUNT_API+'?channel='+ch[0]+'&day='+today+'&sort='+afAgiSort,
            chCtrl ? { signal: chCtrl.signal } : (agiCtrl ? { signal: agiCtrl.signal } : {}));
          if(chTimer) clearTimeout(chTimer);
          if(!r.ok) continue;
          var j = await r.json();
          (j&&j.items||[]).forEach(function(it){
            var k=_normT(it.title);
            if(!seen.has(k)){seen.add(k); merged.push(Object.assign({},it,{_src:'agihunt',_ch:ch[0]}));}
          });
        }catch(e){ if(chTimer) clearTimeout(chTimer); }
      }
      if(agiTimer) clearTimeout(agiTimer);
    })();

    // 等待 AIHOT + AGI Hunt 全部 settle（各自已有超时保护）
    await Promise.allSettled([aihotP, agihuntP]);
    afItems = merged;
    afItems.sort(function(a,b){return (b.publishedAt||b.published_at||'').localeCompare(a.publishedAt||a.published_at||'');});
    afLoaded = true;
    _renderAll();
    _translateAfItems();
    if(!afItems.length){
      upd.textContent = 'AI 动态流';
      list.innerHTML = '<div class="af-empty">暂无动态，请稍后重试</div>';
    } else {
      upd.textContent = 'AI 动态流 · ' + afItems.length + ' 条 · 更新于 ' + new Date().toLocaleTimeString('zh-CN',{hour12:false});
    }

    // ③ 异步追加 /api/news：超时 12s
    var newsCtrl = (typeof AbortController === 'function') ? new AbortController() : null;
    var newsTimer = newsCtrl ? setTimeout(function(){ newsCtrl.abort(); }, 12000) : null;
    fetch('https://starhub-refresh.vercel.app/api/news', newsCtrl ? { signal: newsCtrl.signal } : {}).then(function(r){
      if(newsTimer) clearTimeout(newsTimer);
      return r.ok?r.json():null;
    }).then(function(nj){
      if(!nj||!nj.items||!nj.items.length) return;
      var cutoff=Date.now()-24*3600000;
      var seen2=new Set(afItems.map(function(x){return _normT(x.title);}));
      nj.items.filter(function(it){return it.title&&it.link&&(!it.publishedAt||new Date(it.publishedAt).getTime()>=cutoff);})
        .slice(0,15).forEach(function(it){
          var k=_normT(it.title); if(!seen2.has(k)){seen2.add(k);
            afItems.push({title:it.title,category:'industry',source:{name:it.source||'36氪'},links:{original:it.link},publishedAt:it.publishedAt||'',selected:false,_src:'aihot'});
          }
        });
      afItems.sort(function(a,b){return (b.publishedAt||b.published_at||'').localeCompare(a.publishedAt||a.published_at||'');});
      _renderAll();
    }).catch(function(){ if(newsTimer) clearTimeout(newsTimer); });
  }

  /* ── AI 动态条目 → 分享卡片 ART 结构（复用卡片墙分享链路） ── */
  function _afToArt(it){
    if(!it) return null;
    if(it._src==='agihunt'){
      var chInfo = AGIHUNT_CHANNELS.filter(function(c){return c[0]===it._ch;})[0];
      return {t:it.title||'', s:'', c:chInfo?chInfo[1]:'AGI Hunt', sc:(chInfo&&chInfo[2])||'#6366f1',
        src:it.author||'AGI Hunt', u:it.url||'', time:_fmtRel(it.published_at), _af:true};
    }
    var ci = AIHOT_CATS[it.category] || ['动态','#8b949e'];
    return {t:it.title||'', s:'', c:ci[0], sc:ci[1],
      src:(it.source&&it.source.name)||'AIHOT', u:(it.links&&(it.links.original||it.links.aihot))||'',
      time:_fmtRel(it.publishedAt), _af:true};
  }

  function _renderAll(){
    var list = document.getElementById('afList');
    var filterBox = document.getElementById('afFilter');
    var moreBtn = document.getElementById('afLoadMore');
    // 筛选条：全部 / AIHOT分类 / AGI Hunt频道
    var filtered = afItems;
    if(afFilter !== 'all'){
      if(afFilter.startsWith('ch:')){
        var ch = afFilter.slice(3);
        filtered = afItems.filter(function(it){return it._ch===ch;});
      } else {
        filtered = afItems.filter(function(it){return it._src==='aihot'&&it.category===afFilter;});
      }
    }
    if(afItems.length){
      filterBox.style.display = '';
      var chips = [['all','全部',afItems.length]];
      // AIHOT 分类
      Object.keys(AIHOT_CATS).forEach(function(k){
        var n = afItems.filter(function(it){return it._src==='aihot'&&it.category===k;}).length;
        if(n) chips.push([k,AIHOT_CATS[k][0],n]);
      });
      // AGI Hunt 频道
      AGIHUNT_CHANNELS.forEach(function(c){
        var n = afItems.filter(function(it){return it._ch===c[0];}).length;
        if(n) chips.push(['ch:'+c[0],c[1],n]);
      });
      filterBox.innerHTML = chips.map(function(c){
        return '<button class="fchip'+(afFilter===c[0]?' on':'')+'" data-cat="'+c[0]+'">'+c[1]+' <span class="n">'+c[2]+'</span></button>';
      }).join('');
      // AGI Hunt 排序切换（仅选中频道时显示）
      if(afFilter.indexOf('ch:')===0){
        filterBox.innerHTML += '<button class="fchip" data-sort="'+(afAgiSort==='hot'?'new':'hot')+'" style="margin-left:auto">'+(afAgiSort==='hot'?'→ 最新':'→ 最热')+'</button>';
      }
      filterBox.querySelectorAll('.fchip').forEach(function(chip){
        chip.addEventListener('click', function(){
          var cat = chip.getAttribute('data-cat');
          if(cat){ afFilter=cat; _renderAll(); }
          var sort = chip.getAttribute('data-sort');
          if(sort){ afAgiSort=sort; _refetchAgiChannel(); }
        });
      });
    } else { filterBox.style.display = 'none'; }
    // 列表
    if(!filtered.length){ list.innerHTML = '<div class="af-empty">暂无动态</div>'; moreBtn.style.display='none'; return; }
    list.innerHTML = filtered.map(function(it, i){
      var isAgi = it._src==='agihunt';
      var cat, url, src, tm;
      if(isAgi){
        var chInfo = AGIHUNT_CHANNELS.filter(function(c){return c[0]===it._ch;})[0];
        cat = [chInfo?chInfo[1]:'动态',(chInfo&&chInfo[2])||'#6366f1'];
        url = it.url || '#';
        src = it.author || 'AGI Hunt';
        tm = _fmtRel(it.published_at);
      } else {
        cat = AIHOT_CATS[it.category] || ['动态','#8b949e'];
        url = (it.links&&(it.links.original||it.links.aihot)) || '#';
        src = (it.source&&it.source.name)||'';
        tm = _fmtRel(it.publishedAt);
      }
      var title = it._zh || it.title || '';
      return '<div class="af-item"><span class="cat" style="color:'+cat[1]+';background:'+cat[1]+'1a">'+_escH(cat[0])+'</span>'
        +'<div class="body"><a class="t" href="'+_escH(url)+'" target="_blank" rel="noopener" title="'+_escH(it.title||'')+'">'+_escH(title)+'</a>'
        +'<span class="meta">'+_escH(src)+(src&&tm?' · ':'')+_escH(tm)+(it.selected?' · ★ 精选':'')+'</span></div>'
        +'<button class="af-share" data-i="'+i+'" title="分享"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg></button></div>';
    }).join('');
    // 分享：转为 ART 结构后走统一分享链路（全文 API + 3s 超时降级摘要）
    list.querySelectorAll('.af-share').forEach(function(btn){
      btn.addEventListener('click', function(ev){
        ev.preventDefault(); ev.stopPropagation();
        var art = _afToArt(filtered[parseInt(btn.getAttribute('data-i'),10)]||null);
        if(art) shareArticle(art, null, btn);
      });
    });
    moreBtn.style.display = (afCursor && afFilter==='all') ? '' : 'none';
  }

  // 加载更多（仅 AIHOT 游标分页）
  document.getElementById('afLoadMore').addEventListener('click', async function(){
    var btn = this; if(!afCursor) return;
    btn.disabled = true; btn.textContent = '加载中…';
    try{
      var r = await fetch(AIHOT_API + '&cursor=' + encodeURIComponent(afCursor));
      if(!r.ok) throw new Error('http '+r.status);
      var j = await r.json();
      afCursor = (j.page&&j.page.hasMore) ? (j.page.nextCursor||'') : '';
      var seen = new Set(afItems.map(function(x){return _normT(x.title);}));
      (j.items||[]).forEach(function(it){var k=_normT(it.title);if(!seen.has(k)){seen.add(k);afItems.push(Object.assign({},it,{_src:'aihot'}));}});
      _renderAll();
      _translateAfItems();
    }catch(e){ /* ignore */ }
    btn.disabled = false; btn.textContent = '加载更多';
  });

  /* ── 重取当前 AGI Hunt 频道（排序切换） ── */
  async function _refetchAgiChannel(){
    var ch = afFilter.slice(3);
    var today = new Date(Date.now()+8*3600000).toISOString().slice(0,10);
    try{
      var r = await fetch(AGIHUNT_API+'?channel='+ch+'&day='+today+'&sort='+afAgiSort);
      if(!r.ok) return;
      var j = await r.json();
      var newItems = (j&&j.items||[]).map(function(it){return Object.assign({},it,{_src:'agihunt',_ch:ch});});
      afItems = afItems.filter(function(it){return !(it._src==='agihunt'&&it._ch===ch);});
      var seen = new Set(afItems.map(function(x){return _normT(x.title);}));
      newItems.forEach(function(it){
        var k=_normT(it.title);
        if(!seen.has(k)){seen.add(k); afItems.push(it);}
      });
      afItems.sort(function(a,b){return (b.publishedAt||b.published_at||'').localeCompare(a.publishedAt||a.published_at||'');});
      _renderAll();
      _translateAfItems();
    }catch(e){ /* ignore */ }
  }

  /* ── 自动刷新：每 5 分钟（面板打开时；桌面端 ≥1280px 常驻侧栏始终视为打开） ── */
  function _aiDesktop(){ return window.matchMedia('(min-width:1280px)').matches; }
  setInterval(function(){
    if(document.hidden || afRefreshing) return;
    if(!document.body.classList.contains('ai-open') && !_aiDesktop()) return;
    refreshAiFeed();
  }, 5*60*1000);
  /* 桌面端常驻侧栏：进入页面即加载 AI 动态（移动端保持点击按钮后加载） */
  if(_aiDesktop() && !afLoaded) _loadAll();

  /* ══════════════════════════════════════════
     面板 Tab：AI 快讯 / 全网热榜
     ══════════════════════════════════════════ */
  var afTab='feed';
  var _hotLoaded=false,_hotLoading=false,_hotData=null;
  function switchAfTab(tab){
    afTab=tab;
    document.body.classList.toggle('af-tab-hot',tab==='hot');
    var tf=document.getElementById('afTabFeed'),th=document.getElementById('afTabHot');
    if(tf){tf.classList.toggle('on',tab==='feed');tf.setAttribute('aria-selected',tab==='feed'?'true':'false');}
    if(th){th.classList.toggle('on',tab==='hot');th.setAttribute('aria-selected',tab==='hot'?'true':'false');}
    var hw=document.getElementById('hpWrap');
    if(hw) hw.style.display=(tab==='hot')?'flex':'none';
    var rb=document.getElementById('afRefreshBtn'); if(rb) rb.style.display=''; /* D6: 双 Tab 均显示刷新按钮 */
    var hb=document.getElementById('btnHot'); if(hb) hb.classList.toggle('on',tab==='hot'&&document.body.classList.contains('ai-open'));
    if(tab==='hot'&&!_hotLoaded) loadHotSnapshot();
  }
  window.switchAfTab=switchAfTab;
  var _hotPlatformNames={weibo:'微博',zhihu:'知乎',baidu:'百度',bilibili:'B站',douyin:'抖音',ithome:'IT之家',hackernews:'Hacker News',github:'GitHub',solidot:'Solidot',sspai:'少数派',juejin:'掘金',v2ex:'V2EX',producthunt:'Product Hunt',aihot:'AIHOT',chongbuluo:'虫部落',pcbeta:'远景论坛',nowcoder:'牛客',coolapk:'酷安',xueqiu:'雪球',zaobao:'联合早报',wallstreetcn:'华尔街见闻',cls:'财联社',jin10:'金十数据',gelonghui:'格隆汇',fastbull:'法布财经',toutiao:'今日头条',tencent:'腾讯新闻',thepaper:'澎湃新闻',ifeng:'凤凰网',cankaoxiaoxi:'参考消息',sputniknewscn:'卫星通讯社',kaopu:'靠谱',mktnews:'市场资讯',douban:'豆瓣',tieba:'贴吧',hupu:'虎扑',steam:'Steam',iqiyi:'爱奇艺',qqvideo:'腾讯视频',dongqiudi:'懂球帝'};
  /* dot：平台品牌色（未选中态圆点，提供平台色差区分）；deep：选中态实底色（加深变体，白字对比 ≥4.4:1，明暗主题均可读） */
  var _hotPlatformColors={weibo:'#ff4400',zhihu:'#0066ff',baidu:'#2932e1',bilibili:'#fb7299',douyin:'#fe2c55',ithome:'#d32f2f',hackernews:'#ff6600',github:'#6e5491',solidot:'#4caf50',sspai:'#da3325',juejin:'#1e80ff',v2ex:'#778087',producthunt:'#da552f',aihot:'#0891b2',chongbuluo:'#558b2f',pcbeta:'#1565c0',nowcoder:'#0097a7',coolapk:'#10b981',xueqiu:'#1e88e5',zaobao:'#c62828',wallstreetcn:'#1565c0',cls:'#0277bd',jin10:'#ef6c00',gelonghui:'#00897b',fastbull:'#f57c00',toutiao:'#d32f2f',tencent:'#1976d2',thepaper:'#c62828',ifeng:'#e64a19',cankaoxiaoxi:'#ad1457',sputniknewscn:'#283593',kaopu:'#2e7d32',mktnews:'#4e342e',douban:'#007722',tieba:'#4caf50',hupu:'#d32f2f',steam:'#1b2838',iqiyi:'#00be07',qqvideo:'#ff6900',dongqiudi:'#2e7d32'};
  var _hotPlatformDeep={weibo:'#d5380f',zhihu:'#0052cc',baidu:'#1f28b8',bilibili:'#c73a6c',douyin:'#d9284a',ithome:'#b71c1c',hackernews:'#cc5200',github:'#4a3769',solidot:'#2e7d32',sspai:'#b71c1c',juejin:'#1565c0',v2ex:'#5a5f66',producthunt:'#b5441f',aihot:'#067090',chongbuluo:'#33691e',pcbeta:'#0d47a1',nowcoder:'#006064',coolapk:'#047857',xueqiu:'#1565c0',zaobao:'#8e0000',wallstreetcn:'#0d47a1',cls:'#01579b',jin10:'#e65100',gelonghui:'#00695c',fastbull:'#ef6c00',toutiao:'#b71c1c',tencent:'#0d47a1',thepaper:'#8e0000',ifeng:'#bf360c',cankaoxiaoxi:'#78002e',sputniknewscn:'#1a237e',kaopu:'#1b5e20',mktnews:'#3e2723',douban:'#004400',tieba:'#2e7d32',hupu:'#b71c1c',steam:'#0d1117',iqiyi:'#007a07',qqvideo:'#cc5400',dongqiudi:'#1b5e20'};
  /* 分类筛选：key→中文名，members 为平台 ID 数组 */
  var _hotCats=[
    {key:'all',name:'全部',members:[]},
    {key:'hot',name:'热搜',members:['weibo','zhihu','baidu','bilibili','douyin']},
    {key:'tech',name:'科技',members:['ithome','hackernews','github','solidot','sspai','juejin','v2ex','producthunt','aihot','chongbuluo','pcbeta','nowcoder','coolapk']},
    {key:'biz',name:'财经',members:['xueqiu','zaobao','wallstreetcn','cls','jin10','gelonghui','fastbull']},
    {key:'news',name:'资讯',members:['toutiao','tencent','thepaper','ifeng','cankaoxiaoxi','sputniknewscn','kaopu','mktnews']},
    {key:'life',name:'生活',members:['douban','tieba','hupu','steam','iqiyi','qqvideo','dongqiudi']}
  ];
  var _hotCatKey='all';
  window.toggleHotPanel=function(){
    var panelOpen=document.body.classList.contains('ai-open');
    if(panelOpen&&afTab==='hot'){toggleAiFeed();return;} /* 已在热榜 Tab→再次点击关闭抽屉（移动端习惯） */
    if(!panelOpen) toggleAiFeed();
    switchAfTab('hot');
  };
  var _platExpanded=false;
  function _applyPlatCollapse(){
    var row=document.getElementById('hpTabs');
    if(row) row.classList.toggle('collapsed',window.innerWidth<900&&!_platExpanded);
  }
  /* 平台→分类映射：根据平台 ID 返回所属分类 key */
  function _platCat(p){
    for(var i=0;i<_hotCats.length;i++){
      if(_hotCats[i].members&&_hotCats[i].members.indexOf(p)!==-1) return _hotCats[i].key;
    }
    return 'all';
  }
  function loadHotSnapshot(){
    if(_hotLoading || _hotLoaded) return;
    _hotLoading=true;
    var list=document.getElementById('hotList');
    if(!list) return;
    list.innerHTML='<div class="hp-empty">加载中…</div>';
    fetch('hot_snapshot.json',{cache:'no-cache'}).then(function(r){
      if(!r.ok) throw new Error('HTTP '+r.status);
      return r.json();
    }).then(function(data){
      _hotLoaded=true;_hotLoading=false;
      _hotData=(data||[]).filter(function(s){return s.items&&s.items.length;});
      if(!_hotData.length){list.innerHTML='<div class="hp-empty">暂无热榜数据</div>';return;}
      /* 分类筛选行 → 分段控件（WS-A2） */
      var segEl=document.getElementById('hpCats');
      if(segEl){
        segEl.className='hp-seg';
        segEl.setAttribute('role','tablist');
        segEl.innerHTML=_hotCats.map(function(c){
          return '<button class="hp-seg-btn'+(c.key==='all'?' on':'')+'" role="tab" aria-selected="'+(c.key==='all')+'" data-cat="'+c.key+'">'+c.name+'</button>';
        }).join('');
        segEl.querySelectorAll('.hp-seg-btn').forEach(function(b){
          b.addEventListener('click',function(){_filterHotCat(b.getAttribute('data-cat'));});
        });
      }
      /* 平台 chips（WS-A3） */
      var row=document.getElementById('hpTabs');
      row.className='plat-row collapsed';
      row.innerHTML=_hotData.map(function(s){
        var p=s.platform;
        return '<button class="plat-chip" data-p="'+p+'" data-cat="'+_platCat(p)+'"><span class="dot" style="background:'+(_hotPlatformColors[p]||'#888')+'"></span>'+(_hotPlatformNames[p]||p)+'</button>';
      }).join('');
      /* 展开/收起按钮（WS-A4 移动端折叠） */
      var moreHtml='<button class="plat-more" id="btnPlatMore" aria-expanded="false"><span>全部 '+_hotData.length+' 个</span>';
      moreHtml+='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M6 9l6 6 6-6"/></svg></button>';
      var wrap=row.parentNode.querySelector('.plat-wrap');
      if(wrap){var existing=document.getElementById('btnPlatMore');if(!existing) row.insertAdjacentHTML('afterend',moreHtml);}
      var moreBtn=document.getElementById('btnPlatMore');
      if(moreBtn){
        moreBtn.onclick=function(){
          _platExpanded=!_platExpanded;
          row.classList.toggle('collapsed',window.innerWidth<900&&!_platExpanded);
          moreBtn.querySelector('span').textContent=_platExpanded?'收起':'全部 '+_visiblePlats().length+' 个';
          moreBtn.classList.toggle('open',_platExpanded);
          moreBtn.setAttribute('aria-expanded',_platExpanded);
        };
      }
      row.querySelectorAll('.plat-chip').forEach(function(b){
        b.addEventListener('click',function(){renderHotPlat(b.getAttribute('data-p'),true);});
      });
      renderHotPlat(_hotData[0].platform);
      _applyPlatCollapse();
    }).catch(function(){
      _hotLoading=false;
      list.innerHTML='<div class="hp-empty">加载失败，请稍后重试</div>';
    });
  }
  function _visiblePlats(){
    return _hotData.filter(function(s){return _hotCatKey==='all'||_platCat(s.platform)===_hotCatKey;});
  }
  /* 分类筛选：切换平台 chips 可见性（WS-A5 交互反馈） */
  function _filterHotCat(cat){
    _hotCatKey=cat;
    var segEl=document.getElementById('hpCats');
    if(segEl) segEl.querySelectorAll('.hp-seg-btn').forEach(function(b){
      var on=b.getAttribute('data-cat')===cat;
      b.classList.toggle('on',on);
      b.setAttribute('aria-selected',on);
    });
    var chips=document.getElementById('hpTabs');
    var firstVisible=null;
    chips.querySelectorAll('.plat-chip').forEach(function(b){
      var show=(cat==='all'||b.getAttribute('data-cat')===cat);
      b.style.display=show?'':'none';
      if(show&&!firstVisible) firstVisible=b;
    });
    /* 更新展开按钮计数 */
    var moreBtn=document.getElementById('btnPlatMore');
    if(moreBtn&&!_platExpanded){
      var vis=_visiblePlats();
      moreBtn.querySelector('span').textContent='全部 '+vis.length+' 个';
    }
    /* 如果当前选中的平台被隐藏，自动切到第一个可见平台（带 fade 反馈） */
    var curChip=chips.querySelector('.plat-chip.on');
    if(curChip&&curChip.style.display==='none'&&firstVisible){
      renderHotPlat(firstVisible.getAttribute('data-p'),true);
    }
    /* 分类切换后平台行滚回起点 */
    chips.scrollLeft=0;
  }
  function renderHotPlat(p,swap){
    var chips=document.getElementById('hpTabs');
    chips.querySelectorAll('.plat-chip').forEach(function(b){
      var on=b.getAttribute('data-p')===p;
      b.classList.toggle('on',on);
      b.style.background=on?(_hotPlatformDeep[p]||'#555'):'';
    });
    var list=document.getElementById('hotList');
    var src=null;
    for(var i=0;i<_hotData.length;i++){ if(_hotData[i].platform===p){src=_hotData[i];break;} }
    if(!src){list.innerHTML='<div class="hp-empty">暂无热榜数据</div>';return;}
    var h='';
    var platTrends=(ANALYSIS_DATA&&ANALYSIS_DATA.hot_trends&&ANALYSIS_DATA.hot_trends[p])||{};
    for(var j=0;j<src.items.length;j++){
      var it=src.items[j],rk=it.rank||(j+1),cls=rk<=3?' top3':'';
      var hotTxt=it.hot?(''+it.hot).replace(/^(\d+)(\d{4,})$/,function(m,a,b){return a+'万';}):'';
      h+='<a class="hp-item" href="'+_escH(it.url||'#')+'" target="_blank" rel="noopener">';
      h+='<span class="hp-rank'+cls+'">'+rk+'</span>';
      h+='<span class="hp-title">'+_escH(it.title||'')+'</span>';
      if(hotTxt) h+='<span class="hp-hot">'+hotTxt+'</span>';
      var td=platTrends[it.title||''];
      if(td&&td.trend==='rising') h+='<span class="hp-trend t-up">↑'+td.rise+'</span>';
      else if(td&&td.trend==='falling') h+='<span class="hp-trend t-down">↓'+Math.abs(td.rise)+'</span>';
      else if(td&&td.trend==='new') h+='<span class="hp-trend t-new">新</span>';
      h+='</a>';
    }
    list.innerHTML=h||'<div class="hp-empty">暂无热榜数据</div>';
    /* 分类切换 fade 动画（WS-A5） */
    if(swap&&!matchMedia('(prefers-reduced-motion:reduce)').matches){
      list.classList.remove('hp-swap');void list.offsetWidth;list.classList.add('hp-swap');
    }
  }
  window.addEventListener('resize',function(){ _applyPlatCollapse(); });

  /* ── Insight Panel（每日洞察 · WS-B 容器化） ── */
  var _insightScrollY=0;
  function toggleInsight(){
    var panel=document.getElementById('insightPanel');
    var btn=document.getElementById('btnInsight');
    if(!panel)return;
    var opening=!panel.classList.contains('open');
    if(opening){ renderInsight(); }
    panel.classList.toggle('open',opening);
    if(btn){
      btn.classList.toggle('on',opening);
      btn.setAttribute('aria-expanded',opening);
    }
    /* 遮罩 + 滚动锁 */
    var scrim=document.getElementById('scrim');
    if(scrim) scrim.classList.toggle('on',opening);
    if(opening){
      _insightScrollY=window.scrollY;
      document.body.style.overflow='hidden';
      panel.querySelector('.ip-close').focus();
    } else {
      document.body.style.overflow='';
      window.scrollTo(0,_insightScrollY);
      if(btn) btn.focus();
    }
  }
  window.toggleInsight=toggleInsight;
  function closeInsight(){
    var p=document.getElementById('insightPanel');
    if(p&&p.classList.contains('open')) toggleInsight();
  }

  function renderInsight(){
    var el=document.getElementById('insightBody');
    if(!el||!ANALYSIS_DATA)return;
    var d=ANALYSIS_DATA, h='';
    /* D2: SVG 图标替代 emoji，与站内线性图标体系一致 */
    var _ico={chart:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="width:13px;height:13px"><path d="M3 3v18h18"/><path d="M7 16l4-8 4 4 5-6"/></svg>',bell:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="width:13px;height:13px"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>',signal:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="width:13px;height:13px"><path d="M2 20h.01"/><path d="M7 20v-4"/><path d="M12 20v-8"/><path d="M17 20V8"/><path d="M22 4v16"/></svg>',clock:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="width:13px;height:13px"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>',search:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="width:13px;height:13px"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>',bolt:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="width:13px;height:13px"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>',crystal:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="width:13px;height:13px"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>',tag:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="width:13px;height:13px"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>',flame:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="width:13px;height:13px"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/></svg>'};
    /* WS-C 前端去重兆底 */
    var _dedupSeen=new Set(), _dedupCount=0;
    function _dedup(text){ var t=String(text||'').trim(); if(!t) return ''; var key=t.slice(0,120); if(_dedupSeen.has(key)){_dedupCount++;return '';} _dedupSeen.add(key);return t; }
    /* signals 规范化 */
    function _normSignals(raw){
      return (Array.isArray(raw)?raw:[]).map(function(s){
        if(s&&typeof s==='object') return {signal:s.signal||s.label||s.name||s.text||'',conf:s.confidence};
        var m=String(s).match(/['"]?signal['"]?\s*:\s*['"]([^'"]+)['"]/);
        var c=String(s).match(/['"]?confidence['"]?\s*:\s*([\d.]+)/);
        return {signal:m?m[1]:String(s),conf:c?parseFloat(c[1]):null};
      }).filter(function(x){return x.signal;});
    }
    // 统计摘要
    if(d.stats||d.generated_at){
      h+='<div class="ib-stats">';
      if(d.stats){
        h+='<span>'+_ico.chart+' 文章: '+d.stats.total_articles+'</span>';
        h+='<span>'+_ico.bell+' 近24h: '+d.stats.recent_count+'</span>';
        h+='<span>'+_ico.signal+' 信源: '+d.stats.source_count+'</span>';
      }
      if(d.generated_at) h+='<span>'+_ico.clock+' '+(d.generated_at||'').slice(0,16).replace('T',' ')+'</span>';
      h+='</div>';
      h+='<div style="font-size:10.5px;color:var(--faint);padding:0 0 6px;">数据范围: 近 72 小时滚动窗口</div>';
    }
    // AI 摘要（支持结构化 dict 和旧格式 string）
    if(d.summary){
      if(typeof d.summary==='object'&&!Array.isArray(d.summary)){
        h+='<div class="ib-section"><div class="ib-label">AI 情报分析</div>';
        h+='<div class="ib-sub-grid">';
        var sections=[
          {k:'core_trends',cls:'sub-core',l:'核心态势'},
          {k:'signals',cls:'sub-signal',l:'异动信号'},
          {k:'rss_insights',cls:'sub-rss',l:'RSS洞察'},
          {k:'outlook',cls:'sub-outlook',l:'研判建议'}
        ];
        sections.forEach(function(s){
          if(d.summary[s.k]){
            h+='<div class="ib-sub-section '+s.cls+'">';
            h+='<div class="ib-sub-label">'+s.l+'</div>';
            h+='<div class="ib-sub-text">'+esc(d.summary[s.k])+'</div>';
            h+='</div>';
          }
        });
        h+='</div></div>';
      } else if(typeof d.summary==='string'){
        h+='<div class="ib-section"><div class="ib-label">AI 摘要</div>';
        h+='<div class="ib-summary">'+esc(d.summary)+'</div></div>';
      }
    }
    // 深度洞察 (deep_insights)
    if(d.deep_insights){
      var di=d.deep_insights;
      if(di.narrative){
        h+='<div class="ib-section"><div class="ib-label">'+_ico.search+' 叙事脉络</div>';
        h+='<div class="ib-narrative">'+esc(di.narrative)+'</div></div>';
      }
      if(di.causal_chains&&di.causal_chains.length){
        h+='<div class="ib-section"><div class="ib-label">'+_ico.bolt+' 因果链</div><div class="ib-chain-grid">';
        di.causal_chains.forEach(function(c){
          h+='<div class="ib-chain-card">';
          if(typeof c==='string'){
            h+='<div class="ib-chain-steps">'+esc(c)+'</div>';
          } else {
            h+='<div class="ib-chain-title">'+esc(c.title||c.name||'因果关系')+'</div>';
            h+='<div class="ib-chain-steps">'+esc(c.chain||c.description||'')+'</div>';
          }
          h+='</div>';
        });
        h+='</div></div>';
      }
      if(di.signals&&di.signals.length){
        h+='<div class="ib-section"><div class="ib-label">'+_ico.signal+' 信号看板</div><div class="ib-signal-grid">';
        di.signals.forEach(function(s){
          h+='<div class="ib-signal-card">'+esc(s.label||s.name||s.text||s.signal||'')+'</div>';
        });
        h+='</div></div>';
      }
      if(di.outlook){
        h+='<div class="ib-section"><div class="ib-label">'+_ico.crystal+' 趋势展望</div>';
        h+='<div class="ib-outlook">'+esc(di.outlook)+'</div></div>';
      }
    }
    // 话题聚类 (topic_clusters)
    if(d.topic_clusters&&d.topic_clusters.length){
      var maxCnt=0;
      d.topic_clusters.forEach(function(c){if(c.count>maxCnt)maxCnt=c.count;});
      h+='<div class="ib-section"><div class="ib-label">'+_ico.chart+' 话题聚类</div><div class="ib-cluster-list">';
      d.topic_clusters.slice(0,12).forEach(function(c){
        var pct=maxCnt>0?Math.round(c.count/maxCnt*100):0;
        h+='<div class="ib-cluster-card" data-kw="'+esc(c.label||'')+'" onclick="insightSearch(this.dataset.kw)">';
        h+='<div class="ib-cluster-head"><span class="ib-cluster-label">'+esc(c.label||'未命名')+'</span>';
        h+='<span class="ib-cluster-count">'+c.count+' 篇</span></div>';
        h+='<div class="ib-cluster-bar"><div class="ib-cluster-bar-fill" style="width:'+pct+'%"></div></div>';
        h+='</div>';
      });
      h+='</div></div>';
    }
    // 热门关键词（带生命周期标记）
    if(d.keywords&&d.keywords.global&&d.keywords.global.length){
      var risingSet={};
      if(d.rising) d.rising.forEach(function(r){risingSet[r.word]=r.rise;});
      var kwTraj=(d.rss_trajectories&&d.rss_trajectories.keywords)||{};
      h+='<div class="ib-section"><div class="ib-label">热门关键词</div><div class="ib-kw-list">';
      d.keywords.global.slice(0,30).forEach(function(kw,idx){
        var w=kw[0],score=kw[1],isRising=risingSet[w];
        var traj=kwTraj[w]||{};
        var lc=traj.lifecycle||'';
        var tip='#'+(idx+1)+' 得分:'+score.toFixed(2);
        if(isRising) tip+=' (上升'+isRising+'位)';
        if(lc) tip+=' | 轨迹:'+lc;
        if(traj.first_seen) tip+=' | 首次:'+traj.first_seen.slice(5,16).replace('T',' ');
        if(traj.duration) tip+=' | 持续:'+traj.duration+'周期';
        var cls='ib-kw';
        if(lc==='emergent') cls+=' kw-emergent kw-tag';
        else if(lc==='rising') cls+=' kw-rising kw-tag';
        else if(lc==='peaking') cls+=' kw-peaking kw-tag';
        else if(lc==='declining') cls+=' kw-declining kw-tag';
        else if(lc==='gone') cls+=' kw-gone kw-tag';
        else if(isRising) cls+=' rising';
        h+='<span class="'+cls+'" data-kw="'+esc(w)+'" title="'+tip+'" onclick="insightSearch(this.dataset.kw)">'+esc(w)+'</span>';
      });
      h+='</div></div>';
    }
    // 升温关键词
    if(d.rising&&d.rising.length){
      h+='<div class="ib-section"><div class="ib-label">⬆️ 升温词</div><div class="ib-kw-list">';
      d.rising.forEach(function(r){
        h+='<span class="ib-kw rising" data-kw="'+esc(r.word)+'" onclick="insightSearch(this.dataset.kw)" title="排名上升 '+r.rise+' 位">'+esc(r.word)+'</span>';
      });
      h+='</div></div>';
    }
    // 今日话题
    if(d.topics&&d.topics.length){
      h+='<div class="ib-section"><div class="ib-label">今日话题</div><div class="ib-topic-list">';
      d.topics.slice(0,12).forEach(function(t,i){
        var rk=i+1, cls=rk<=3?' top3':'';
        var tl=(t.label||(t.labels&&t.labels.length?t.labels.join(' '):''));
        var src=t.sources?(Array.isArray(t.sources)?t.sources.length:t.sources):0;
        h+='<div class="ib-topic" data-kw="'+esc(tl)+'" onclick="insightSearch(this.dataset.kw)">';
        h+='<span class="ib-topic-rank'+cls+'">'+rk+'</span>';
        h+='<span class="ib-topic-title">'+esc(tl)+'</span>';
        h+='<span class="ib-topic-meta">'+t.count+' 篇 · '+src+' 源</span>';
        h+='</div>';
      });
      h+='</div></div>';
    }
    // 话题趋势（跨周期轨迹）
    var topicTraj=(d.rss_trajectories&&d.rss_trajectories.topics)||{};
    if(d.topics&&d.topics.length&&Object.keys(topicTraj).length>0){
      h+='<div class="ib-section ib-trend"><div class="ib-trend-title">📈 话题趋势</div><div class="ib-trend-list">';
      d.topics.slice(0,10).forEach(function(t){
        var tl=(t.label||(t.labels&&t.labels.length?t.labels.join(' '):''));
        var traj=topicTraj[tl]||{};
        var lc=traj.lifecycle||'emerging';
        var cnt=t.count||0;
        var arrow='', arrowCls='';
        if(lc==='hot'){arrow='🔥';arrowCls='t-hot';}
        else if(lc==='emerging'){arrow='⬆';arrowCls='t-up';}
        else if(lc==='cooling'){arrow='⬇';arrowCls='t-down';}
        else if(lc==='cold'){arrow='❄';arrowCls='t-down';}
        var lcLabel={emerging:'新兴',hot:'火爆',cooling:'降温',cold:'冷却'}[lc]||lc;
        h+='<div class="ib-trend-item" data-kw="'+esc(tl)+'" onclick="insightSearch(this.dataset.kw)">';
        h+='<span class="ib-trend-label">'+esc(tl)+'</span>';
        h+='<span class="ib-trend-count">'+cnt+'篇</span>';
        if(arrow) h+='<span class="ib-trend-arrow '+arrowCls+'">'+arrow+'</span>';
        h+='<span class="ib-trend-lc lc-'+lc+'">'+lcLabel+'</span>';
        h+='</div>';
      });
      h+='</div></div>';
    }
    // 跨平台共振
    if(d.cross_platform&&d.cross_platform.length){
      h+='<div class="ib-section ib-cross"><div class="ib-label">跨平台共振</div><div class="ib-cross-list">';
      d.cross_platform.slice(0,8).forEach(function(m){
        h+='<div class="ib-cross-item">';
        if(m.platforms&&m.platforms.length){
          h+='<span class="ib-cross-label">'+esc(m.label)+'</span>';
          h+='<span class="ib-cross-plats">';
          m.platforms.forEach(function(p){
            h+='<span class="ib-cross-plat">'+esc(p.name)+'</span>';
          });
          h+='</span>';
        } else {
          h+='<span class="ib-cross-label">'+esc(m.title_a||m.label||'')+'</span>';
          h+='<span class="ib-cross-plats">';
          h+='<span class="ib-cross-plat">'+esc(m.platform_a||'')+'</span>';
          h+='<span class="ib-cross-plat">'+esc(m.platform_b||'')+'</span>';
          h+='</span>';
        }
        h+='</div>';
      });
      h+='</div></div>';
    }
    // 跨分类热点
    if(d.cross_category&&d.cross_category.length){
      h+='<div class="ib-section ib-ccat"><div class="ib-label">🌐 跨分类热点</div><div class="ib-ccat-list">';
      d.cross_category.slice(0,12).forEach(function(cc){
        h+='<div class="ib-ccat-item" data-kw="'+esc(cc.keyword)+'" onclick="insightSearch(this.dataset.kw)">';
        h+='<span class="ib-ccat-kw">'+esc(cc.keyword)+'</span>';
        h+='<span class="ib-ccat-cats">';
        cc.categories.forEach(function(c){
          h+='<span class="ib-ccat-cat">'+esc(c)+'</span>';
        });
        h+='</span></div>';
      });
      h+='</div></div>';
    }
    if(!h) h='<div class="ib-no-data">暂无分析数据</div>';
    /* WS-C 去重提示 */
    if(_dedupCount>0) h+='<div class="ip-dedup"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M20 6L9 17l-5-5"/></svg>已自动跳过 '+_dedupCount+' 段与上文重复的内容</div>';
    el.innerHTML=h;
    /* 锚点导航（WS-B2） */
    var navEl=document.getElementById('ipNav');
    if(navEl){
      var secs=el.querySelectorAll('.ib-section, .ip-sec');
      var navHtml='';
      secs.forEach(function(s,i){
        var label=(s.querySelector('.ib-label, .ip-label')||{}).textContent||'';
        if(!label) return;
        if(!s.id) s.id='ip-sec-'+i;
        navHtml+='<button data-t="'+s.id+'" class="'+(i===0?'on':'')+'">'+label+'</button>';
      });
      navEl.innerHTML=navHtml;
      navEl.querySelectorAll('button').forEach(function(b){
        b.onclick=function(){
          navEl.querySelectorAll('button').forEach(function(x){x.classList.remove('on');});
          b.classList.add('on');
          var target=document.getElementById(b.dataset.t);
          if(target) target.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth',block:'start'});
        };
      });
    }
  }

  function insightSearch(keyword){
    var bg=null;
    // 长标签（话题/趋势）→ 提取字符二元组做模糊匹配
    var clean=keyword.replace(/^\[RSS\/\w+\]\s*/,'');
    if(clean.length>15){
      var low=clean.toLowerCase(),arr=[];
      for(var i=0;i<low.length-1;i++){
        var c=low[i],n=low[i+1];
        if(c.trim()&&n.trim()&&c!==n) arr.push(c+n);
      }
      var seen={},uniq=[];
      arr.forEach(function(b){if(!seen[b]){seen[b]=1;uniq.push(b);}});
      if(uniq.length>=2) bg=uniq;
    }
    var si=document.getElementById('globalSearch');
    if(si){si.value=keyword;si.dispatchEvent(new Event('input'));}
    // input handler 会重置 _topicBigrams=null，所以在 dispatch 之后赋值
    _topicBigrams=bg;
    window.scrollTo({top:0,behavior:'smooth'});
    setTimeout(function(){
      var first=document.querySelector('.wall .card');
      if(first) first.scrollIntoView({behavior:'smooth',block:'center'});
    },150);
  }
  window.insightSearch=insightSearch;

})();
