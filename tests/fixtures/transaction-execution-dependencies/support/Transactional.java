package org.springframework.transaction.annotation;
public @interface Transactional {
    Propagation propagation() default Propagation.REQUIRED;
}
