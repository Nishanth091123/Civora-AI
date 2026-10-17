"""Preliminary quantity takeoff, not a substitute for approved mix/structural design."""
import math

WORKS={'brickwork':'Brick masonry','blockwork':'AAC block masonry','pcc':'PCC concrete','rcc':'RCC concrete (grade-based planning)','plaster':'Cement plaster','flooring':'Floor tiles','painting':'Wall painting','excavation':'Earthwork excavation (volume)','backfill':'Backfilling / compacted fill','shuttering':'Formwork / shuttering','waterproofing':'Waterproofing membrane / coating','screed':'Floor screed / levelling','steel':'Reinforcement steel (BBS input)'}
UNIT_TO_M={'mm':0.001,'in':0.0254,'ft':0.3048,'m':1.0}
MORTAR_RATIOS=tuple(f'1:{n}' for n in range(3,9))
PCC_RATIOS={'1:3:6':(1,3,6),'1:4:8':(1,4,8),'1:5:10':(1,5,10)}
RCC_GRADES=tuple(f'M{n}' for n in range(15,55,5))

def convert_length(value,unit):
    if unit not in UNIT_TO_M or not math.isfinite(value) or value<0: raise ValueError('Invalid unit or dimension')
    return value*UNIT_TO_M[unit]

def takeoff(work,length,width,depth,openings=0,waste=5,brick_length=.19,brick_height=.09,brick_width=.09,joint=.01,tile_length=.6,tile_width=.6,coats=2,paint_coverage=10,adhesive_coverage=5.0,unit='m',mortar_ratio='1:6',plaster_ratio='1:4',pcc_ratio='1:4:8',rcc_grade='M20',rcc_mode='rmc',rcc_site_method='nominal',rcc_nominal_ratio='1:1.5:3',opening_length=None,opening_width=None,rcc_cement_kg=0,rcc_msand_kg=0,rcc_aggregate_kg=0,rcc_water_l=0,rcc_admixture_kg=0,steel_kg_m3=0,material_coverage=1,material_bag_kg=25,steel_diameter_mm=12,steel_total_length_m=0,steel_bar_count=0,steel_cut_length_m=0):
    if work not in WORKS: raise ValueError('Unknown work')
    if unit not in UNIT_TO_M: raise ValueError('Unsupported unit')
    values=(length,width,depth,openings,waste,brick_length,brick_height,brick_width,joint,tile_length,tile_width,paint_coverage,adhesive_coverage,rcc_cement_kg,rcc_msand_kg,rcc_aggregate_kg,rcc_water_l,rcc_admixture_kg,steel_kg_m3,material_coverage,material_bag_kg,steel_diameter_mm,steel_total_length_m,steel_bar_count,steel_cut_length_m)
    if not all(math.isfinite(x) for x in values): raise ValueError('Values must be finite')
    if not (0<length<=100000 and 0<width<=100000 and 0<depth<=100000 and 0<=waste<=30): raise ValueError('Invalid dimensions or wastage')
    if work=='blockwork' and not (1<=adhesive_coverage<=20): raise ValueError('AAC adhesive dry-powder coverage must be 1–20 kg/m²')
    if work=='brickwork' and mortar_ratio not in MORTAR_RATIOS: raise ValueError('Unsupported masonry mortar ratio')
    if work=='plaster' and plaster_ratio not in MORTAR_RATIOS: raise ValueError('Unsupported plaster mortar ratio')
    if work=='pcc' and pcc_ratio not in PCC_RATIOS: raise ValueError('Unsupported PCC ratio')
    if work=='rcc' and rcc_grade not in RCC_GRADES: raise ValueError('Unsupported RCC grade')
    # Every dimensional field uses the same user-selected unit; opening area is entered in unit².
    factor=UNIT_TO_M[unit]; l=length*factor; w=width*factor; d=depth*factor
    area=l*w-openings*factor**2
    if not (area>0): raise ValueError('Opening deduction exceeds measured area')
    vol=area*d
    if not (vol<1e12): raise ValueError('Volume too large')
    items=[]; notes=[]
    def add(name,qty,u,basis):
        if not math.isfinite(qty) or qty<0 or qty>1e12: raise ValueError('Material quantity out of range')
        items.append({'material':name,'quantity':round(qty*(1+waste/100),3),'unit':u,'basis':basis})
    def mortar(wet,ratio):
        parts=int(ratio.split(':')[1]); dry=wet*1.33
        add('Cement',dry/(1+parts)*1440/50,'bags (50 kg)',f'Mortar {ratio}; dry factor 1.33, bulk density 1440 kg/m³')
        add('Sand',dry*parts/(1+parts),'m³',f'Mortar {ratio}; dry factor 1.33')
    if work in ('brickwork','blockwork'):
        bl,bh,bw,j=(brick_length,brick_height,brick_width,joint)
        if min(bl,bh,bw)<=0 or max(bl,bh,bw)>3 or j<0 or j>.05: raise ValueError('Invalid brick or joint dimensions')
        if work=='blockwork' and not (.003<=j<=.005): raise ValueError('AAC thin-bed adhesive thickness must be 3–5 mm')
        module=(bl+j)*(bh+j)*(bw+j)
        count=vol/module
        wet=max(0,vol-count*bl*bh*bw)
        blocks=math.ceil(math.ceil(count)*(1+waste/100))
        items.append({'material':'Bricks' if work=='brickwork' else 'AAC blocks','quantity':blocks,'unit':'nos','basis':'Whole units rounded up after wastage; modular size approximation'})
        if work=='brickwork':
            mortar(wet,mortar_ratio)
        else:
            # AAC dry powder kg/m² is a configurable product-specific coverage assumption.
            # Do not convert theoretical wet joint volume to powder weight without density.
            adhesive_kg=area*adhesive_coverage*(1+waste/100)
            bags=math.ceil(adhesive_kg/40)
            items.append({'material':'AAC thin-bed adhesive powder','quantity':round(adhesive_kg,2),'unit':'kg','basis':f'{adhesive_coverage:g} kg/m² coverage × {area:.3f} m² × wastage'})
            items.append({'material':'AAC adhesive 40 kg bags','quantity':bags,'unit':'bags (40 kg)','basis':'Rounded up from dry powder kg; verify actual bag size and product coverage'})
            notes.append('Adhesive dry-powder consumption is based on the editable manufacturer coverage assumption, not inferred from wet joint volume. Confirm coverage for block size, substrate and trowel before ordering.')
    elif work=='pcc':
        ratio=PCC_RATIOS[pcc_ratio];dry=vol*1.54; total=sum(ratio)
        add('Cement',dry*ratio[0]/total*1440/50,'bags (50 kg)',f'Nominal PCC {pcc_ratio}; dry factor 1.54')
        add('Sand',dry*ratio[1]/total,'m³',f'Nominal PCC {pcc_ratio}')
        add('Coarse aggregate',dry*ratio[2]/total,'m³',f'Nominal PCC {pcc_ratio}')
    elif work=='rcc':
        if rcc_mode not in ('rmc','site'): raise ValueError('Select RMC or Site Mix')
        if rcc_mode=='rmc':
            add('Ready-mix concrete (RMC)',vol,'m³',f'{rcc_grade}; ready-mix concrete supply quantity')
            notes.append('RMC quantity only. Order specification and wastage allowance must be confirmed with supplier.')
        else:
            if rcc_site_method not in ('nominal','design'): raise ValueError('Select nominal or approved design mix')
            if rcc_site_method=='nominal':
                if rcc_nominal_ratio not in ('1:1.5:3','1:2:4','1:3:6'):
                    raise ValueError('Unsupported nominal ratio')
                if rcc_grade!='M20' or rcc_nominal_ratio!='1:1.5:3':
                    raise ValueError('Only M20 1:1.5:3 is offered as an illustrative nominal RCC option. Other grades require approved design mix.')
                dry=vol*1.54
                c,s,ag=(1,1.5,3); total=c+s+ag
                cement_kg=dry*c/total*1440
                add('Cement',cement_kg,'kg','Illustrative M20 nominal 1:1.5:3; dry volume factor 1.54; density 1440 kg/m³')
                items.append({'material':'Cement 50 kg bags','quantity':math.ceil(cement_kg*(1+waste/100)/50),'unit':'bags (50 kg)','basis':'Rounded up after wastage; alternative representation of cement kg'})
                add('M-sand',dry*s/total,'m³','Illustrative nominal ratio by dry volume')
                add('Coarse aggregate',dry*ag/total,'m³','Illustrative nominal ratio by dry volume')
                notes.append('M20 1:1.5:3 is an illustrative nominal estimate only, not an approved concrete mix. Structural RCC often requires design mix, material tests and engineer approval. Water/admixture quantities are not inferred from this ratio.')
            else:
                rates=(rcc_cement_kg,rcc_msand_kg,rcc_aggregate_kg,rcc_water_l,rcc_admixture_kg)
                if any(x<0 or x>5000 for x in rates): raise ValueError('Invalid approved mix constituent rate')
                if not all(x>0 for x in rates[:4]): raise ValueError('Enter approved mix cement, M-sand, aggregate and water per m³')
                add('Cement',vol*rcc_cement_kg,'kg',f'Approved mix {rcc_cement_kg:g} kg/m³')
                items.append({'material':'Cement 50 kg bags','quantity':math.ceil(vol*rcc_cement_kg*(1+waste/100)/50),'unit':'bags (50 kg)','basis':'Whole bags; alternative to cement kg'})
                add('M-sand',vol*rcc_msand_kg,'kg',f'Approved mix {rcc_msand_kg:g} kg/m³')
                add('Coarse aggregate',vol*rcc_aggregate_kg,'kg',f'Approved mix {rcc_aggregate_kg:g} kg/m³')
                add('Mixing water',vol*rcc_water_l,'litres',f'Approved mix {rcc_water_l:g} L/m³')
                if rcc_admixture_kg: add('Admixture',vol*rcc_admixture_kg,'kg',f'Approved mix {rcc_admixture_kg:g} kg/m³')
            if not (0<=steel_kg_m3<=500): raise ValueError('Invalid steel planning rate')
            if steel_kg_m3: add('Steel planning allowance (not BBS)',vol*steel_kg_m3,'kg',f'User-supplied {steel_kg_m3:g} kg/m³; verify from approved BBS')
    elif work=='plaster':
        mortar(vol,plaster_ratio)
    elif work=='flooring':
        tl,tw=tile_length,tile_width
        if not (0<tl<=5 and 0<tw<=5): raise ValueError('Invalid tile dimensions')
        items.append({'material':'Tiles','quantity':math.ceil(math.ceil(area/(tl*tw))*(1+waste/100)),'unit':'nos','basis':'Whole tiles rounded up after wastage; no layout optimization'})
        add('Tile adhesive',area*4,'kg','Illustrative 4 kg/m²; verify product')
    elif work=='excavation':
        add('Excavated earth (in-situ volume)',vol,'m³','Length × width × depth minus any plan-area deductions; no bulking or disposal factor')
        notes.append('Excavation is geometric in-situ quantity only. Soil bulking, slope/battering, shoring, dewatering, haulage and safety checks are excluded.')
    elif work=='backfill':
        add('Compacted backfill',vol,'m³','Compacted geometric quantity; supply bulking/compaction factors separately')
        notes.append('Compaction, soil source, layer thickness and laboratory density must be verified.')
    elif work=='shuttering':
        add('Formwork contact area',area,'m²','Length × width less openings; count actual concrete-contact faces separately')
        notes.append('Do not multiply by thickness. Enter each face separately; props, supports and reuse cycles excluded.')
    elif work=='waterproofing':
        if not (0<material_coverage<=30): raise ValueError('Invalid membrane/coating consumption')
        add('Waterproofing material',area*material_coverage,'kg',f'{material_coverage:g} kg/m² product-specific coverage')
        notes.append('Confirm number of coats, overlaps, upstands and manufacturer consumption.')
    elif work=='screed':
        mortar(vol,plaster_ratio)
        notes.append('Screed uses an illustrative cement:sand mortar ratio. Confirm approved specification.')
    elif work=='steel':
        if not (6<=steel_diameter_mm<=50): raise ValueError('Invalid bar diameter')
        if steel_bar_count>0:
            if steel_bar_count!=int(steel_bar_count) or steel_bar_count>100000 or not (0<steel_cut_length_m<=100000): raise ValueError('Invalid bar count or cut length')
            total_length=steel_bar_count*steel_cut_length_m
            notes.append(f'{int(steel_bar_count)} bars × {steel_cut_length_m:g} m cut length per bar = {total_length:g} m. Include bends, hooks and laps in cut length.')
        else:
            if not (0<steel_total_length_m<=1e7): raise ValueError('Enter total cut length or bar count × cut length')
            total_length=steel_total_length_m
        unit_weight=steel_diameter_mm**2/162
        kg=unit_weight*total_length
        add('Reinforcement steel',kg,'kg',f'{steel_diameter_mm:g} mm × {total_length:g} m total; {unit_weight:.4f} kg/m (D²/162)')
        notes.append('Preliminary weight based on theoretical unit mass. Cutting schedule, laps, hooks, bends and approved drawings control final quantity; do not treat as structural design.')
    elif work=='painting':
        if not (1<=coats<=6 and 1<=paint_coverage<=30): raise ValueError('Invalid painting inputs')
        add('Paint',area*coats/paint_coverage,'litres','Coats and declared coverage')
        add('Primer',area/10,'litres','Illustrative one coat, 10 m²/L')
    return {'work':WORKS[work],'net_area_m2':round(area,4),'net_volume_m3':round(vol,4),'waste_pct':waste,'items':items,'notes':notes,'unit':unit,'selection':{'mortar_ratio':mortar_ratio,'plaster_ratio':plaster_ratio,'pcc_ratio':pcc_ratio,'rcc_grade':rcc_grade,'rcc_mode':rcc_mode,'rcc_site_method':rcc_site_method,'rcc_nominal_ratio':rcc_nominal_ratio,'adhesive_coverage_kg_m2':adhesive_coverage,'rcc_mix_rates_kg_m3':{'cement':rcc_cement_kg,'msand':rcc_msand_kg,'aggregate':rcc_aggregate_kg,'water_l_m3':rcc_water_l,'admixture':rcc_admixture_kg}}}
