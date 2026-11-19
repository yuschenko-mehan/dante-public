POWERSHELL_BLUE="#012456"; POWERSHELL_TEXT="#eeedf0"
CAMPBELL={"red":"#e74856","green":"#16c60c","yellow":"#f9f1a5","blue":"#3b78ff","cyan":"#61d6d6","white":"#f2f2f2"}
def _rgb(c): return [int(c[i:i+2],16) for i in (1,3,5)]
def _hex(r): return "#"+"".join(f"{max(0,min(255,round(x))):02x}" for x in r)
def _mix(a,b,k): A,B=_rgb(a),_rgb(b); return _hex([x+(y-x)*k for x,y in zip(A,B)])
def luminance(c):
    def ch(v):
        v/=255; return v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4
    r,g,b=[ch(v) for v in _rgb(c)]; return 0.2126*r+0.7152*g+0.0722*b
def contrast_ratio(a,b):
    l1,l2=sorted([luminance(a),luminance(b)],reverse=True); return (l1+0.05)/(l2+0.05)
def palette(level):
    lv=max(0,min(100,round(float(level)))); k=min(lv,60)/60; k2=max(0,lv-60)/40
    log_bg=_mix("#000000",POWERSHELL_BLUE,k)
    log_fg=_mix("#7a7a7a",POWERSHELL_TEXT,k**0.5) if lv<=60 else _mix(POWERSHELL_TEXT,"#ffffff",k2)
    bg=_mix("#000000","#0c0c0c",k)
    fg=_mix("#7a7a7a","#e0e0e0",k) if lv<=60 else _mix("#e0e0e0","#ffffff",k2)
    return {"BG":bg,"SURFACE":_mix(bg,"#ffffff",0.06),"SURFACE2":_mix(bg,"#ffffff",0.10),"HOVER":_mix(bg,"#ffffff",0.15),
            "BORDER":_mix("#3a3a3a","#8c8c8c",lv/100),"FG":fg,"FG2":_mix(fg,bg,0.12),"LOG_BG":log_bg,"LOG_FG":log_fg,
            "ACCENT":CAMPBELL["cyan"],"WARN":CAMPBELL["yellow"],"ERR":CAMPBELL["red"],"OK":CAMPBELL["green"]}
def value_from_x(x,width,pad=10):
    span=max(1,width-2*pad); return max(0,min(100,round((x-pad)/span*100)))
def x_from_value(v,width,pad=10):
    span=max(1,width-2*pad); return round(pad+max(0,min(100,v))/100*span)
def step(v,d): return max(0,min(100,v+d))
