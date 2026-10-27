"""Masked artwork matching; never infer an identity from element/color alone."""
from functools import lru_cache
import cv2
import numpy as np
from autotata.paths import ASSETS
from .catalog import load_catalog


def read_image(path):
    return cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_UNCHANGED)


@lru_cache(maxsize=4)
def reference_features(background=None):
    sift = cv2.SIFT_create(nfeatures=220)
    result = []
    for item in load_catalog():
        rgba = read_image(ASSETS/item['imagePath'])
        if rgba is None: raise ValueError('塔塔图片缺失：'+item['name'])
        if rgba.shape[2] == 3: raise ValueError('塔塔图片缺少透明通道：'+item['name'])
        alpha = rgba[:,:,3]; ys, xs = np.where(alpha > 30)
        tight = rgba[ys.min():ys.max()+1, xs.min():xs.max()+1]
        scale = 180/max(tight.shape[:2])
        tight = cv2.resize(tight, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        color = tight[:,:,:3]; mask = tight[:,:,3]
        gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
        if background is not None:
            # Transparent pixels are displayed over the reference board, not
            # black. A neutral rendering avoids background-dependent outline
            # descriptors while preserving the same source artwork and mask.
            gray=np.rint(gray*(mask/255)+background*(1-mask/255)).astype(np.uint8)
        keypoints, descriptors = sift.detectAndCompute(gray, (mask > 100).astype(np.uint8)*255)
        result.append((item['id'], color, mask, keypoints, descriptors))
    return result


@lru_cache(maxsize=4096)
def template_pyramid(identity,height,width):
    """Reuse the immutable artwork scales across cards and fresh frames."""
    _,color,alpha,_,_=next(r for r in reference_features(None) if r[0]==identity)
    variants=[]
    for fraction in np.arange(.50,1.06,.06):
        ratio=height*fraction/color.shape[0]
        tw,th=round(color.shape[1]*ratio),round(color.shape[0]*ratio)
        if min(tw,th)<12 or tw>width or th>height:continue
        image=cv2.cvtColor(cv2.resize(color,(tw,th),interpolation=cv2.INTER_AREA),cv2.COLOR_BGR2GRAY)
        mask=(cv2.resize(alpha,(tw,th),interpolation=cv2.INTER_AREA)>130).astype(np.uint8)*255
        variants.append((image,mask))
    return tuple(variants)


@lru_cache(maxsize=128)
def query_features(height,width,pixels):
    """Target-family searches share descriptors for identical visible portraits."""
    roi=np.frombuffer(pixels,np.uint8).reshape(height,width,3)
    gray=cv2.cvtColor(roi,cv2.COLOR_BGR2GRAY)
    ratio=min(1.,80/max(height,width))
    small=cv2.resize(gray,None,fx=ratio,fy=ratio,interpolation=cv2.INTER_AREA)
    points,desc=cv2.SIFT_create(nfeatures=250).detectAndCompute(gray,None)
    return small,points,desc


def root_descriptors(descriptors):
    return np.sqrt(descriptors/(descriptors.sum(axis=1,keepdims=True)+1e-9)).astype(np.float32)


@lru_cache(maxsize=1)
def root_reference_features():
    return {identity:root_descriptors(desc) for identity,_,_,_,desc in reference_features(180) if desc is not None}


def pose_consensus(roi,points,desc,models,center_region):
    """Recover a small animated body with independent geometric/color checks.

    RootSIFT changes descriptor normalization, not the general acceptance
    threshold. Sparse fits require broad, non-collinear body support, precise
    reprojection, matching appearance and an unambiguous identity.
    """
    if desc is None or len(desc)<5:return None
    query=root_descriptors(desc);references=root_reference_features();matcher=cv2.BFMatcher();accepted=[]
    gray=cv2.cvtColor(roi,cv2.COLOR_BGR2GRAY)
    for identity,color,alpha,ref_points,_ in models:
        reference=references.get(identity)
        if reference is None:continue
        pairs=matcher.knnMatch(reference,query,k=2)
        unique={}
        for a,b in pairs:
            if a.distance<.70*b.distance and (a.trainIdx not in unique or a.distance<unique[a.trainIdx].distance):unique[a.trainIdx]=a
        good=list(unique.values())
        if len(good)<5:continue
        src=np.float32([ref_points[m.queryIdx].pt for m in good]);dst=np.float32([points[m.trainIdx].pt for m in good])
        transform,inliers=cv2.estimateAffinePartial2D(src,dst,method=cv2.RANSAC,ransacReprojThreshold=2.5)
        if transform is None or inliers is None:continue
        selected=inliers.ravel().astype(bool);count=int(selected.sum())
        if count<5 or count/len(good)<.70:continue
        body=src[selected];coverage=np.ptp(body,axis=0)/np.array([color.shape[1],color.shape[0]])
        if coverage[0]<.35 or coverage[1]<.50 or np.prod(coverage)<.20:continue
        if cv2.contourArea(cv2.convexHull(body))/(color.shape[0]*color.shape[1])<.08:continue
        residual=np.median(np.linalg.norm(body@transform[:,:2].T+transform[:,2]-dst[selected],axis=1))
        if residual>1.4:continue
        scale=float(np.hypot(*transform[:,1]));angle=abs(np.degrees(np.arctan2(transform[1,0],transform[0,0])))
        cx,cy=transform@np.array([color.shape[1]/2,color.shape[0]/2,1])
        if angle>25 or not .25*roi.shape[0]<=scale*color.shape[0]<=1.6*roi.shape[0]:continue
        if not 0<=cx<=roi.shape[1] or not 0<=cy<=roi.shape[0]:continue
        if center_region is not None and not (center_region[0]<=cx<=center_region[2] and center_region[1]<=cy<=center_region[3]):continue
        warped=cv2.warpAffine(color,transform,(roi.shape[1],roi.shape[0]));mask=cv2.warpAffine(alpha,transform,(roi.shape[1],roi.shape[0]))>200
        if np.count_nonzero(mask)<100:continue
        appearance=cv2.cvtColor(warped,cv2.COLOR_BGR2GRAY)[mask];observed=gray[mask]
        if min(float(appearance.std()),float(observed.std()))<8:continue
        correlation=float(np.corrcoef(appearance,observed)[0,1])
        error=float(np.median(np.abs(warped[mask].astype(float)-roi[mask]).mean(axis=1)))
        if not np.isfinite(correlation) or correlation<.30 or error>50:continue
        accepted.append(identity)
    if len(set(accepted))!=1:return None
    return {'id':accepted[0],'score':.88,'candidates':[{'id':accepted[0],'score':.88}]}


@lru_cache(maxsize=128)
def cached_pose_consensus(height,width,pixels,identities,center_region):
    roi=np.frombuffer(pixels,np.uint8).reshape(height,width,3)
    _,points,desc=query_features(height,width,pixels)
    allowed=set(identities)
    return pose_consensus(roi,points,desc,[r for r in reference_features(180) if r[0] in allowed],center_region)


def identify(roi, minimum=.80, allowed_ids=None,center_region=None,animated=False,background=None):
    if roi is None or roi.size == 0: return {'id': '?', 'score': 0., 'candidates': []}
    if roi.shape[2] == 4: roi = roi[:,:,:3]
    if max(roi.shape[:2]) < 180:
        ratio=180/max(roi.shape[:2])
        roi=cv2.resize(roi,None,fx=ratio,fy=ratio,interpolation=cv2.INTER_CUBIC)
        if center_region is not None:center_region=tuple(v*ratio for v in center_region)
    small,points,desc=query_features(*roi.shape[:2],roi.tobytes())
    matcher = cv2.BFMatcher()
    features=[]
    models=[r for r in reference_features(background) if allowed_ids is None or r[0] in allowed_ids]
    for identity, color, alpha, ref_points, reference in models:
        if allowed_ids is not None and identity not in allowed_ids:continue
        feature_score = 0.
        if desc is not None and len(desc) >= 2 and reference is not None:
            pairs=matcher.knnMatch(reference,desc,k=2)
            for tolerance in ((.68,.70) if animated else (.68,)):
                good = [a for a, b in pairs if a.distance < tolerance*b.distance]
                unique = {}
                for match in good:
                    if match.trainIdx not in unique or match.distance < unique[match.trainIdx].distance:
                        unique[match.trainIdx] = match
                good = sorted(unique.values(),key=lambda match:match.distance)
                if len(good) >= 5:
                    src = np.float32([ref_points[m.queryIdx].pt for m in good])
                    dst = np.float32([points[m.trainIdx].pt for m in good])
                    # Reference sprites may be stretched within their drawing box.
                    # The fallback is restricted to neutral-rendered poses and
                    # rejects reflection, excessive stretch, and weak body fits.
                    estimators=(cv2.estimateAffinePartial2D,cv2.estimateAffine2D) if animated and background is not None else (cv2.estimateAffinePartial2D,)
                    for estimator in estimators:
                        transform, inliers = estimator(src, dst, method=cv2.RANSAC, ransacReprojThreshold=2.5)
                        if transform is not None and inliers is not None:
                            if estimator is cv2.estimateAffine2D:
                                axes=np.linalg.svd(transform[:,:2],compute_uv=False)
                                if np.linalg.det(transform[:,:2])<=0 or axes[-1]<=0 or axes[0]/axes[-1]>1.5:continue
                            count = int(inliers.sum()); scale = float(np.hypot(*transform[:,1]))
                            cx, cy = transform @ np.array([color.shape[1]/2,color.shape[0]/2,1])
                            spread=np.ptp(src[inliers.ravel().astype(bool)],axis=0)
                            coverage=spread/np.array([color.shape[1],color.shape[0]])
                            predicted=src @ transform[:,:2].T+transform[:,2]
                            residual=np.median(np.linalg.norm(predicted[inliers.ravel().astype(bool)]-dst[inliers.ravel().astype(bool)],axis=1))
                            # Sprite poses include decorative features that may move
                            # independently. A broad, precise eight-point body fit can
                            # establish the pose without accepting clustered badges.
                            coherent=((count>=6 and count/len(good)>=.65) or
                                      (animated and count>=10 and count/len(good)>=.4) or
                                      (animated and count>=8 and count/len(good)>=.4 and
                                       np.all(coverage>=.25) and residual<=1.))
                            if estimator is cv2.estimateAffine2D:
                                coherent=(count>=8 and count/len(good)>=.4 and np.all(coverage>=.25) and residual<=1.)
                            # Small portraits can place their reliable features along a
                            # narrow body. Relax spread only for numerous, consistent
                            # points with enough total coverage; tiny shared details
                            # and scattered matches still cannot establish identity.
                            supported_spread=(np.all(coverage>=.15) or
                                              (count>=9 and count/len(good)>=.8 and
                                               np.all(coverage>=.12) and np.prod(coverage)>=.06))
                            if (coherent and
                                    supported_spread and
                                    .25*roi.shape[0] <= scale*color.shape[0] <= 1.6*roi.shape[0]
                                    and 0 <= cx <= roi.shape[1] and 0 <= cy <= roi.shape[0]
                                    and (center_region is None or center_region[0]<=cx<=center_region[2] and center_region[1]<=cy<=center_region[3])):
                                feature_score = min(.96, .68+count*.025)
                                break
                if feature_score:break
        features.append((feature_score,identity))
    ordered=sorted(features,reverse=True)
    # A targeted search may use any owned stage in one evolution family. Its
    # coherent six-point fit is sufficient; broad catalog searches retain the
    # eight-point fast path and still compare ambiguous poses with templates.
    family_search=allowed_ids is not None and len({r['family'] for r in load_catalog() if r['id'] in allowed_ids})==1
    feature_minimum=.83 if family_search else .88
    if ordered and ordered[0][0]>=max(feature_minimum,minimum) and (len(ordered)==1 or ordered[0][0]-ordered[1][0]>=.10):
        return {'id':ordered[0][1],'score':round(ordered[0][0],3),
                'candidates':[{'id':k,'score':round(s,3)} for s,k in ordered[:3]]}
    feature_scores={k:s for s,k in features};scores=[]
    for identity,color,alpha,_,_ in models:
        best = 0.
        for image,mask in template_pyramid(identity,*small.shape):
            th,tw=image.shape
            match = cv2.matchTemplate(small, image, cv2.TM_CCOEFF_NORMED, mask=mask)
            match[~np.isfinite(match)] = -1
            if center_region is not None:
                left,top,right,bottom=[v*min(1.,80/max(roi.shape[:2])) for v in center_region]
                x0=max(0,int(np.ceil(left-tw/2)));x1=min(match.shape[1],int(np.floor(right-tw/2))+1)
                y0=max(0,int(np.ceil(top-th/2)));y1=min(match.shape[0],int(np.floor(bottom-th/2))+1)
                match=match[y0:y1,x0:x1]
                if not match.size:continue
            best = max(best, float(match.max()))
        scores.append((max(best, feature_scores[identity]), identity))
    scores.sort(reverse=True)
    if not scores:return {'id':'?','score':0.,'candidates':[]}
    best, identity = scores[0]
    margin = best-scores[1][0] if len(scores)>1 else best
    known = best >= minimum and margin >= .035
    if not known and animated and background==180 and best>=.40:
        recovered=cached_pose_consensus(*roi.shape[:2],roi.tobytes(),tuple(r[0] for r in models),tuple(center_region) if center_region is not None else None)
        if recovered is not None and recovered['score']>=minimum:return recovered
    return {'id': identity if known else '?', 'score': round(best, 3),
            'candidates': [{'id': ident, 'score': round(score, 3)} for score, ident in scores[:3]]}


class PortraitCache:
    """Session-only acceleration from already confirmed inventory portraits."""
    def __init__(self):self.templates={}
    @staticmethod
    def normalize(image):
        return cv2.resize(image[:,:,:3],(64,64),interpolation=cv2.INTER_AREA)
    def add(self,identity,image):
        if identity=='?':return
        values=self.templates.setdefault(identity,[])
        if len(values)<3:values.append(self.normalize(image))
    def match(self,image,allowed_ids=None):
        target=self.normalize(image);scores=[]
        for identity,variants in self.templates.items():
            if allowed_ids is not None and identity not in allowed_ids:continue
            score=max(float(cv2.matchTemplate(target,template,cv2.TM_CCOEFF_NORMED)[0,0]) for template in variants)
            if np.isfinite(score):scores.append((score,identity))
        scores.sort(reverse=True)
        if not scores:return None
        best,identity=scores[0];runner_up=scores[1][0] if len(scores)>1 else 0
        if best<.95 or best-runner_up<.08:return None
        return {'id':identity,'score':round(best,3),'candidates':[{'id':k,'score':round(s,3)} for s,k in scores[:3]]}
