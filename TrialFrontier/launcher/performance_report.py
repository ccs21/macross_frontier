"""Schema 2 bounded capture reader. CPU stages are wall time, not CPU samples."""
import struct
from pathlib import Path

CPU_FIELDS=['qpc','fetch','state_targets','pipeline_lookup','textures','constants_bind','backend_draw',
    'depth_readback_nested','depth_pack_nested','fetch_refs_nested','fetch_remap_nested',
    'fetch_prepare_nested','fetch_decode_nested','fifo_idle','fifo_active','spu_runner_wall',
    'spu_runner_cycles','spu_runner_calls','frame_limiter','all_fences','swapchain_acquire',
    'queue_present','present_mutex','fifo_idle_calls','fifo_active_calls','present_thread_cpu_100ns',
    'process_cpu_100ns','present_thread_id','clock_valid_mask','schema','reserved0','reserved1']
WAIT_KINDS={1:'transfer_begin_including_draw_flush',2:'submit_and_wait',3:'fence_nested',
            4:'swapchain_acquire',5:'queue_present_including_queue_lock',6:'present_mutex',7:'frame_limiter'}
LIMITS={'frames.bin':1296008,'waits.bin':4194312,'cpu.bin':4608008}

def read_records(path,width):
    with Path(path).open('rb') as stream:data=stream.read(LIMITS[Path(path).name]+1)
    if len(data)<8:raise ValueError('missing clock header')
    if len(data)>LIMITS[Path(path).name]:raise ValueError('capture exceeded size bound')
    frequency=struct.unpack_from('<Q',data)[0]
    if not frequency:raise ValueError('zero clock frequency')
    stride=width*8;end=8+(len(data)-8)//stride*stride
    return frequency,sorted(struct.iter_unpack('<'+'Q'*width,data[8:end]),key=lambda row:row[0]),len(data)-end

def summarize(folder):
    folder=Path(folder);result={'schema':2,'files':{},'issues':[],
        'cpu_fields':CPU_FIELDS,'wait_kinds':WAIT_KINDS,
        'interpretation':'Stages 0-5 are sequential draw phases; nested depth/fetch stages and fence waits overlap parents. SPU runner wall sums concurrent jobs and includes waits; cycles are not milliseconds. No hardware GPU timestamps. Present thread CPU deltas require matching thread IDs. Uninstrumented remainder is not automatically CPU or SPU.'}
    loaded={}
    for name,width in [('frames.bin',9),('waits.bin',4),('cpu.bin',32)]:
        try:
            freq,rows,tail=read_records(folder/name,width);loaded[name]=(freq,rows)
            result['files'][name]={'records':len(rows),'frequency':freq,'partial_tail_bytes':tail}
            if not rows:result['issues'].append(name+': no records')
            if tail:result['issues'].append(name+': incomplete final record')
        except (OSError,ValueError,struct.error) as e:result['issues'].append(name+': '+str(e))
    if len({v[0] for v in loaded.values()})>1:result['issues'].append('clock frequencies do not match')
    if 'cpu.bin' in loaded and loaded['cpu.bin'][1]:
        freq,rows=loaded['cpu.bin'];last=rows[-1]
        result['observed_nonzero_fields']=[CPU_FIELDS[i] for i in range(1,27) if last[i]>0]
        for i in list(range(1,7))+[13,14,17,23,24]:
            if not last[i]:result['issues'].append('no observed '+CPU_FIELDS[i]+'; scene/path coverage not established')
        if any(r[29]!=2 or r[28]!=3 for r in rows):result['issues'].append('invalid schema or OS CPU clock read failed')
        # Only compare exact shared present timestamps. No guessed offset.
        frames=dict((r[0],r) for r in loaded.get('frames.bin',(0,[]))[1])
        matched=[r for r in rows if r[0] in frames]
        result['matched_present_records']=len(matched)
        if not matched:result['issues'].append('no exact CPU/present timestamp match')
        slow=[]
        for a,b in zip(matched,matched[1:]):
            interval=(b[0]-a[0])*1000/freq
            if interval<40:continue
            values={CPU_FIELDS[i]:(b[i]-a[i])*1000/freq for i in list(range(1,16))+list(range(18,23))}
            slow.append({'qpc':b[0],'interval_ms':interval,'wall_ms':values,
                'spu_calls':b[17]-a[17],'spu_cycles':b[16]-a[16],
                'process_cpu_ms':(b[26]-a[26])/10000,
                'present_thread_cpu_ms':(b[25]-a[25])/10000 if b[27]==a[27] else None})
        result['slow_frame_count']=len(slow)
        result['slow_frames']=sorted(slow,key=lambda row:-row['interval_ms'])[:120]
        result['summary_limit']='120 longest matched intervals; all retained samples remain in binary files'
    return result
