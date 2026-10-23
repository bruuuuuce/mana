package fixture;
import org.springframework.stereotype.Service;
@Service class Entry extends MissingBase {
    public void run() { inherited(); }
}
