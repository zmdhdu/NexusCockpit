import pathlib
base=pathlib.Path(chr(100)+chr(58)+chr(92))
pats=[chr(118)+chr(50)+chr(46)+chr(48)+chr(32)]
files=list(base.glob(chr(100)+chr(111)+chr(99)+chr(115)+chr(47)+chr(42)+chr(42)+chr(47)+chr(42)+chr(46)+chr(109)+chr(100)))
c=0
for f in files:
  t=f.read_text(encoding=chr(117)+chr(116)+chr(102)+chr(45)+chr(56))
  o=t
  for pat in pats:
    t=t.replace(pat,chr(0))
  if t!=o:
    f.write_text(t,encoding=chr(117)+chr(116)+chr(102)+chr(45)+chr(56))
    c+=1
print(c)