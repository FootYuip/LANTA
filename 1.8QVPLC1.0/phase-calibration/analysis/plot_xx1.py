"""Offline trace analysis only; no PLC code or controls are modified."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

out = Path(__file__).resolve().parent
a = np.loadtxt(r'C:\Users\fcj\Desktop\XX1.txt', skiprows=3, encoding='utf-8-sig')
t = a[:, 0]/1000
b = a[:, 16:18]
p = a[:, 10:12] - a[t<31.4, 10:12].mean(axis=0)
e = a[:, 3:5]
m = (t>31.4)&(t<64.5)
x = np.column_stack([p, np.ones(len(p))])
c = np.linalg.lstsq(x[m][::10], e[m][::10], rcond=None)[0]
k = c[:2].T
g = np.linalg.norm(k, axis=0)
orth = abs(90-np.degrees(np.arccos(np.dot(k[:,0],k[:,1])/np.prod(g))))
phi = np.degrees(np.arctan2(-k[1,0]/g[0]+k[0,1]/g[1], -k[0,0]/g[0]-k[1,1]/g[1]))
plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'], 'axes.unicode_minus':False, 'font.size':10})
fig, ax = plt.subplots(2,2,figsize=(12,8),layout='constrained')
for j,title in enumerate(['方位：指令偏置与实际变化','俯仰：指令偏置与实际变化']):
    q=ax[0,j]
    q.plot(t-t[0],b[:,j],label='指令偏置',color='#245fa5',lw=1.6)
    q.plot(t-t[0],p[:,j],label='实际变化（相对初始均值）',color='#c46a24',lw=1)
    q.set(title=title,xlabel='记录相对时间（s）',ylabel='角度变化（°）')
    q.legend(fontsize=9);q.grid(alpha=.2)
q=ax[1,0]
for j,name,color in [(0,'Ua','#245fa5'),(1,'Ue','#c46a24')]:
    q.plot(t-t[0],e[:,j]-e[t<31.4,j].mean(),label=name+' 相对初始均值',color=color,lw=.8)
q.set(title='误差电压确实响应了运动',xlabel='记录相对时间（s）',ylabel='电压变化（V）')
q.legend(fontsize=9);q.grid(alpha=.2)
q=ax[1,1]
for j,name,color in [(0,'向右拉偏响应','#245fa5'),(1,'向上拉偏响应','#c46a24')]:
    u=k[:,j]/g[j]
    q.annotate('',xy=u,xytext=(0,0),arrowprops={'arrowstyle':'->','lw':2,'color':color})
    q.plot([],[],color=color,label=name)
q.axhline(0,color='gray',lw=.5);q.axvline(0,color='gray',lw=.5)
q.set(xlim=(-1.1,1.1),ylim=(-1.1,1.1),aspect='equal',xlabel='Ua 归一化响应',ylabel='Ue 归一化响应',title=f'拟合响应夹角 {90-orth:.1f}°，不是 90°')
q.legend(fontsize=8,loc='upper left');q.grid(alpha=.2)
fig.suptitle('XX1 校相诊断：运动已执行，但单一相位旋转模型不合格',fontsize=15)
fig.supxlabel('来源：XX1.txt；时间戳 26.836–76.831 s；拟合窗口 31.4–64.5 s，每 10 点抽取一次。非 PLC 内部样本重放。',fontsize=9)
fig.savefig(out/'XX1-curves.png',dpi=160)
print('matrix V/deg',k,'orth_error',orth,'diagnostic_phase',phi)
