"""Raw-sensor hard/soft-iron calibration with strict ellipsoid/coverage gates.

The symmetric correction preserves volume (determinant 1). Its field magnitude
is a fitted local reference, not a calibrated measurement of geographic north.
No numpy dependency is required in the live receiver or calibration tool.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "config/magnetometer_v1.json"


def _solve(matrix, rhs):
    n = len(rhs)
    rows = [list(row) + [rhs[i]] for i, row in enumerate(matrix)]
    for i in range(n):
        pivot = max(range(i, n), key=lambda r: abs(rows[r][i]))
        rows[i], rows[pivot] = rows[pivot], rows[i]
        if abs(rows[i][i]) < 1e-10:
            raise ValueError("磁场采集欠约束，请覆盖三个轴的完整朝向")
        divisor = rows[i][i]
        rows[i] = [x / divisor for x in rows[i]]
        for r in range(n):
            if r != i:
                factor = rows[r][i]
                rows[r] = [a - factor*b for a, b in zip(rows[r], rows[i])]
    return [row[-1] for row in rows]


def _product(a, b):
    return [[sum(a[i][k]*b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _eigen(matrix):
    a, v = deepcopy(matrix), [[float(i == j) for j in range(3)] for i in range(3)]
    for _ in range(60):
        p, q = max(((0,1),(0,2),(1,2)), key=lambda ij: abs(a[ij[0]][ij[1]]))
        if abs(a[p][q]) < 1e-12:
            break
        theta = .5*math.atan2(2*a[p][q], a[q][q]-a[p][p])
        c, s = math.cos(theta), math.sin(theta)
        r = [[float(i == j) for j in range(3)] for i in range(3)]
        r[p][p] = r[q][q] = c
        r[p][q], r[q][p] = s, -s
        a = _product([list(x) for x in zip(*r)], _product(a, r))
        v = _product(v, r)
    return [a[i][i] for i in range(3)], v


def correct(vector, calibration):
    if calibration is None:
        return tuple(vector)
    delta = [x-b for x,b in zip(vector,calibration["bias_mG"])]
    return tuple(sum(a*b for a,b in zip(row,delta)) for row in calibration["matrix"])


def validate(value):
    result = deepcopy(value)
    if result.get("algorithm") != "ellipsoid-spd/1":
        raise ValueError("不支持的磁校准版本")
    bias, matrix = result.get("bias_mG"), result.get("matrix")
    if (not isinstance(bias,list) or len(bias)!=3 or not isinstance(matrix,list) or len(matrix)!=3
            or any(not isinstance(row,list) or len(row)!=3 for row in matrix)):
        raise ValueError("磁偏置须为三维，校正矩阵须为3×3")
    numbers = bias + [x for row in matrix for x in row]
    if any(type(x) not in (int,float) or not math.isfinite(x) for x in numbers):
        raise ValueError("磁校准含非有限数值")
    if math.hypot(*bias)>5000 or any(abs(matrix[i][j]-matrix[j][i])>1e-8 for i in range(3) for j in range(3)):
        raise ValueError("磁校准偏置或矩阵不合理")
    eigen, _ = _eigen(matrix)
    if min(eigen)<.05 or max(eigen)>20 or max(eigen)/min(eigen)>5:
        raise ValueError("磁校准矩阵不是合理的正定校正")
    if not result.get("quality",{}).get("passed"):
        raise ValueError("磁校准未通过方向覆盖及残差检查")
    result.pop("calibration_id",None)
    encoded = json.dumps(result,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    result["calibration_id"] = "mag-"+hashlib.sha256(encoded).hexdigest()[:16]
    return result


def fit(vectors):
    if len(vectors)<300 or any(len(v)!=3 or any(not math.isfinite(x) for x in v) for v in vectors):
        raise ValueError("至少需要300个有效三维磁场样本")
    n = len(vectors)
    mean = [sum(v[i] for v in vectors)/n for i in range(3)]
    scale = math.sqrt(sum(sum((v[i]-mean[i])**2 for i in range(3)) for v in vectors)/n)
    if scale<10:
        raise ValueError("磁场变化范围不足，请完整转动板子")
    design=[]
    for vector in vectors:
        x,y,z = [(vector[i]-mean[i])/scale for i in range(3)]
        design.append([x*x,y*y,z*z,2*x*y,2*x*z,2*y*z,x,y,z])
    normal = [[sum(row[i]*row[j] for row in design)/n for j in range(9)] for i in range(9)]
    c = _solve(normal,[sum(row[i] for row in design)/n for i in range(9)])
    a = [[c[0],c[3],c[4]],[c[3],c[1],c[5]],[c[4],c[5],c[2]]]
    center = [-.5*x for x in _solve(a,c[6:])]
    divisor = 1+sum(center[i]*a[i][j]*center[j] for i in range(3) for j in range(3))
    if divisor<=0:
        raise ValueError("拟合不是有效椭球")
    eigen, basis = _eigen([[x/divisor for x in row] for row in a])
    if min(eigen)<=0 or max(eigen)/min(eigen)>25:
        raise ValueError("三维磁场拟合不合理：方向覆盖不足或环境磁场变化")
    determinant = math.prod(eigen)**(1/6)
    matrix = [[sum(basis[i][k]*math.sqrt(eigen[k])*basis[j][k] for k in range(3))/determinant
               for j in range(3)] for i in range(3)]
    result = {"algorithm":"ellipsoid-spd/1","bias_mG":[mean[i]+scale*center[i] for i in range(3)],"matrix":matrix}
    corrected = [correct(v,result) for v in vectors]
    radii = [math.hypot(*v) for v in corrected]
    field = sum(radii)/n
    if not 50<=field<=1500 or min(radii)<1:
        raise ValueError("校正后场强不合理，不能应用")
    directions = [[x/r for x in v] for v,r in zip(corrected,radii)]
    octants = [0]*8
    for v in directions:
        octants[sum((1<<i) for i,x in enumerate(v) if x>0)] += 1
    covariance = [[sum(v[i]*v[j] for v in directions)/n for j in range(3)] for i in range(3)]
    coverage, _ = _eigen(covariance)
    rms = math.sqrt(sum((r/field-1)**2 for r in radii)/n)
    full_axes = all(min(v[i] for v in directions)<-.65 and max(v[i] for v in directions)>.65 for i in range(3))
    if not full_axes or min(octants)<max(5,n*.005) or min(coverage)/max(coverage)<.15:
        raise ValueError("方向覆盖不足，请让六个面朝上并绕三个轴完整转动")
    if rms>.08:
        raise ValueError("磁场拟合残差过大，请固定位置并远离变化的磁场")
    result["quality"] = {"passed":True,"samples":n,"field_mG":field,"relative_rms":rms,
                         "octants":octants,"coverage_eigenvalues":coverage}
    return validate(result)


def load(device_id, path=CONFIG):
    if not Path(path).exists():
        return None
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("schema_version")!="magnetometer-config/1":
        raise ValueError("磁校准配置版本错误")
    value = config.get("devices",{}).get(device_id)
    return validate(value) if value else None


def save(device_id, calibration, path=CONFIG):
    calibration = validate(calibration)
    path = Path(path)
    config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"schema_version":"magnetometer-config/1","devices":{}}
    if config.get("schema_version")!="magnetometer-config/1":
        raise ValueError("磁校准配置版本错误")
    config["devices"][device_id] = calibration
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(config,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    temporary.replace(path)
    return calibration
