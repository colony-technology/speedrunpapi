import sys,struct,zlib
F={1:"b",2:"B",3:"h",4:"H",5:"i",6:"I",7:"f",9:"d",12:"q",13:"Q"}
def tag(d,p):
    t,s=struct.unpack("<II",d[p:p+8])
    if t>>16: return t&0xffff,t>>16,p+4,p+8
    return t,s,p+8,p+8+((s+7)//8)*8
def num(d,p):
    t,s,q,nx=tag(d,p);f=F[t];n=s//struct.calcsize(f);return list(struct.unpack("<%d%s"%(n,f),d[q:q+s])),nx
def mat(d,p):
    t,s,q,nx=tag(d,p);cls=d[q];p=nx
    t,s,q,nx=tag(d,p);dims=struct.unpack("<%di"%(s//4),d[q:q+s]);p=nx
    t,s,q,nx=tag(d,p);nm=d[q:q+s].decode();p=nx
    n=1
    for x in dims:n*=x
    if cls==2:
        t,s,q,nx=tag(d,p);fl=struct.unpack("<i",d[q:q+4])[0];p=nx
        t,s,q,nx=tag(d,p);names=[d[q+i:q+i+fl].split(b"\0")[0].decode() for i in range(0,s,fl)];p=nx
        out=[]
        for k in range(n):
            o={}
            for f in names:
                t,s,q,nx=tag(d,p);o[f]=mat(d,q)[1] if s else None;p=nx
            out.append(o)
        return nm,out
    if cls==1:
        out=[]
        for k in range(n):
            t,s,q,nx=tag(d,p);out.append(mat(d,q)[1] if s else None);p=nx
        return nm,out
    if n==0: return nm,("arr",dims,[])
    v,p=num(d,p);return nm,("arr",dims,v)
def load(fn):
    b=open(fn,"rb").read();p=128;r={}
    while p<len(b):
        t,s=struct.unpack("<II",b[p:p+8])
        if t==15:
            d=zlib.decompress(b[p+8:p+8+s]);tt,ss,qq,nn=tag(d,0);k,v=mat(d,qq);r[k]=v
        p+=8+s
    return r
